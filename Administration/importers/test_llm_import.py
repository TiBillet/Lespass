#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for LLM_import.py
"""

import os
import sys
import django

# Setup Django environment
sys.path.append('/home/jonas/TiBillet/dev/Lespass')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

from Administration.importers.LLM_import import import_event_from_text

# Sample text input (in French)
sample_text = """
Concert de Jazz au Café des Arts
Le groupe "Les Improvisateurs" se produira le 15 juin 2023 à 20h30 au Café des Arts.
Adresse: 15 rue de la Musique, 34000 Montpellier, France.
Venez découvrir ce trio de jazz qui revisite les standards avec une touche de modernité.
Le concert se terminera vers 23h. Entrée: 10€.
"""

# Sample HTML input
sample_html = """
<h1>Concert de Jazz au Café des Arts</h1>
<p>Le groupe "Les Improvisateurs" se produira le <strong>15 juin 2023 à 20h30</strong> au Café des Arts.</p>
<p>Adresse: <em>15 rue de la Musique, 34000 Montpellier, France</em>.</p>
<p>Venez découvrir ce trio de jazz qui revisite les standards avec une touche de modernité.</p>
<p>Le concert se terminera vers 23h. Entrée: 10€.</p>
"""

def test_text_import():
    """Test importing an event from plain text"""
    print("Testing plain text import...")
    success, result = import_event_from_text(sample_text)
    
    if success:
        print(f"Success! Created event: {result.name}")
        print(f"Date: {result.datetime}")
        print(f"Address: {result.postal_address}")
        print(f"Description: {result.short_description}")
        print(f"Tags: {', '.join([tag.name for tag in result.tag.all()])}")
    else:
        print(f"Failed: {result}")

def test_html_import():
    """Test importing an event from HTML"""
    print("\nTesting HTML import...")
    success, result = import_event_from_text(sample_html)
    
    if success:
        print(f"Success! Created event: {result.name}")
        print(f"Date: {result.datetime}")
        print(f"Address: {result.postal_address}")
        print(f"Description: {result.short_description}")
        print(f"Tags: {', '.join([tag.name for tag in result.tag.all()])}")
    else:
        print(f"Failed: {result}")

if __name__ == "__main__":
    # Check if OpenAI API key is set
    if not os.environ.get("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY environment variable is not set.")
        print("You can set it with: export OPENAI_API_KEY=your_api_key")
    
    # Run tests
    test_text_import()
    test_html_import()