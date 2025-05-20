#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LLM_import.py - Natural Language Event Importer

This script uses GPT 4.1 nano to parse natural language input (text or HTML)
and create event objects with tags, addresses, and descriptions.
"""

import re
import json
import logging
import html2text
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from openai import OpenAI

from BaseBillet.models import Event, Tag, PostalAddress

logger = logging.getLogger(__name__)

class LLMEventImporter:
    """
    A class that uses LLM to parse natural language input and create event objects.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the LLM Event Importer.
        
        Args:
            api_key: OpenAI API key. If None, will try to use environment variable.
        """
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # GPT 4.1 nano
        
    def _preprocess_input(self, input_text: str) -> str:
        """
        Preprocess the input text, converting HTML to plain text if needed.
        
        Args:
            input_text: The input text, which can be HTML or plain text.
            
        Returns:
            Preprocessed plain text.
        """
        # Check if input is HTML
        if "<" in input_text and ">" in input_text:
            h = html2text.HTML2Text()
            h.ignore_links = False
            return h.handle(input_text)
        return input_text
    
    def _extract_event_data(self, input_text: str) -> Dict:
        """
        Use LLM to extract event data from natural language input.
        
        Args:
            input_text: Preprocessed input text.
            
        Returns:
            Dictionary containing extracted event data.
        """
        prompt = f"""
        Extract event information from the following text. Return a JSON object with these fields:
        - name: Event name
        - datetime: Event start date and time (ISO format)
        - end_datetime: Event end date and time (ISO format), if available
        - location: Venue name
        - address: Full address with street, city, postal code, and country
        - short_description: A brief description (max 100 chars)
        - long_description: A detailed description
        - tags: List of relevant tags/categories
        - categorie: Event type (one of: "LIV" for Concert, "FES" for Festival, "REU" for Meeting, "CON" for Conference, "RES" for Catering, "CHT" for Workcamp, "ACT" for Volunteering)
        
        Text:
        {input_text}
        
        Return only the JSON object, nothing else.
        """
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts structured event information from text."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM response as JSON")
            return {}
    
    def _validate_event_data(self, event_data: Dict) -> Tuple[bool, Dict]:
        """
        Validate the extracted event data and check for hallucinations.
        
        Args:
            event_data: Dictionary containing extracted event data.
            
        Returns:
            Tuple of (is_valid, validated_data)
        """
        # Double-check with a second LLM call to verify the data
        prompt = f"""
        Verify if the following event information is consistent and realistic:
        {json.dumps(event_data, indent=2)}
        
        Check for:
        1. Is the event name reasonable?
        2. Is the date and time format valid and realistic (not in the past)?
        3. Is the location and address information complete and realistic?
        4. Do the tags match the event description?
        5. Is the event category appropriate for the description?
        
        Return a JSON object with:
        - is_valid: true/false
        - issues: list of issues found (empty if valid)
        - corrected_data: corrected event data (if corrections were needed)
        
        Return only the JSON object, nothing else.
        """
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that verifies event information for accuracy and consistency."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            validation_result = json.loads(response.choices[0].message.content)
            if validation_result.get("is_valid", False):
                return True, event_data
            else:
                corrected_data = validation_result.get("corrected_data", event_data)
                issues = validation_result.get("issues", [])
                for issue in issues:
                    logger.warning(f"Event data issue: {issue}")
                return False, corrected_data
        except json.JSONDecodeError:
            logger.error("Failed to parse validation response as JSON")
            return False, event_data
    
    def _create_or_get_postal_address(self, address_data: Dict) -> PostalAddress:
        """
        Create or get a PostalAddress object from address data.
        
        Args:
            address_data: Dictionary containing address information.
            
        Returns:
            PostalAddress object.
        """
        # Parse the full address into components
        full_address = address_data.get("address", "")
        location_name = address_data.get("location", "")
        
        # Try to extract components from the full address
        street_address = full_address
        address_locality = ""
        postal_code = ""
        address_country = "France"  # Default
        
        # Try to extract postal code (French format)
        postal_code_match = re.search(r'\b\d{5}\b', full_address)
        if postal_code_match:
            postal_code = postal_code_match.group(0)
        
        # Try to extract city (usually after postal code in French addresses)
        if postal_code:
            city_match = re.search(rf'{postal_code}\s+([A-Za-z\s\-]+)', full_address)
            if city_match:
                address_locality = city_match.group(1).strip()
        
        # Create or get the postal address
        try:
            address, created = PostalAddress.objects.get_or_create(
                name=location_name,
                defaults={
                    "street_address": street_address,
                    "address_locality": address_locality or "Unknown",
                    "postal_code": postal_code or "00000",
                    "address_country": address_country
                }
            )
            return address
        except Exception as e:
            logger.error(f"Error creating postal address: {e}")
            # Create a new address as fallback
            return PostalAddress.objects.create(
                name=location_name,
                street_address=street_address,
                address_locality="Unknown",
                postal_code="00000",
                address_country="France"
            )
    
    def _create_or_get_tags(self, tag_names: List[str]) -> List[Tag]:
        """
        Create or get Tag objects from tag names.
        
        Args:
            tag_names: List of tag names.
            
        Returns:
            List of Tag objects.
        """
        tags = []
        for name in tag_names:
            tag, created = Tag.objects.get_or_create(name=name)
            tags.append(tag)
        return tags
    
    def _create_event(self, event_data: Dict) -> Event:
        """
        Create an Event object from validated event data.
        
        Args:
            event_data: Dictionary containing validated event data.
            
        Returns:
            Event object.
        """
        # Parse datetime strings
        try:
            datetime_obj = datetime.fromisoformat(event_data.get("datetime"))
        except (ValueError, TypeError):
            # Fallback to current datetime if parsing fails
            datetime_obj = datetime.now()
        
        try:
            end_datetime_obj = datetime.fromisoformat(event_data.get("end_datetime")) if event_data.get("end_datetime") else None
        except (ValueError, TypeError):
            end_datetime_obj = None
        
        # Create or get postal address
        address_data = {
            "location": event_data.get("location", ""),
            "address": event_data.get("address", "")
        }
        postal_address = self._create_or_get_postal_address(address_data)
        
        # Create or get tags
        tags = self._create_or_get_tags(event_data.get("tags", []))
        
        # Create event
        event = Event.objects.create(
            name=event_data.get("name", "Unnamed Event"),
            slug=slugify(event_data.get("name", "unnamed-event")),
            datetime=datetime_obj,
            end_datetime=end_datetime_obj,
            postal_address=postal_address,
            short_description=event_data.get("short_description", "")[:250],  # Ensure it fits in the field
            long_description=event_data.get("long_description", ""),
            categorie=event_data.get("categorie", Event.CONCERT),
            published=True
        )
        
        # Add tags
        for tag in tags:
            event.tag.add(tag)
        
        return event
    
    def import_from_text(self, input_text: str) -> Tuple[bool, Union[Event, str]]:
        """
        Import an event from natural language text.
        
        Args:
            input_text: Natural language text describing an event (can be HTML or plain text).
            
        Returns:
            Tuple of (success, result) where result is either an Event object or an error message.
        """
        try:
            # Preprocess input
            processed_text = self._preprocess_input(input_text)
            
            # Extract event data
            event_data = self._extract_event_data(processed_text)
            if not event_data:
                return False, "Failed to extract event data from input text"
            
            # Validate event data
            is_valid, validated_data = self._validate_event_data(event_data)
            if not is_valid:
                logger.warning("Event data validation failed, using corrected data")
            
            # Create event
            event = self._create_event(validated_data)
            
            return True, event
        except Exception as e:
            logger.exception("Error importing event from text")
            return False, f"Error importing event: {str(e)}"


def import_event_from_text(text: str, api_key: Optional[str] = None) -> Tuple[bool, Union[Event, str]]:
    """
    Import an event from natural language text.
    
    Args:
        text: Natural language text describing an event (can be HTML or plain text).
        api_key: OpenAI API key. If None, will try to use environment variable.
        
    Returns:
        Tuple of (success, result) where result is either an Event object or an error message.
    """
    importer = LLMEventImporter(api_key=api_key)
    return importer.import_from_text(text)