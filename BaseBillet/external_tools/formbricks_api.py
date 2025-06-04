import requests
from typing import Dict, List, Optional, Any, Union
import json
import logging

from BaseBillet.models import FormbricksConfig

logger = logging.getLogger(__name__)

class FormbricksAPI:
    """
    A Python library for interacting with the Formbricks API.

    This library provides methods to:
    - List all available forms (V1 API)
    - Retrieve responses for each form in JSON format (V1 API)
    - Create users (contact attribute keys) (V2 API)

    It uses the API key from BaseBillet.models.FormbricksConfig.get_api_key()
    """

    def __init__(self):
        """Initialize the FormbricksAPI with configuration from FormbricksConfig."""
        config = FormbricksConfig.get_solo()
        self.api_key = config.get_api_key()
        if not self.api_key:
            raise ValueError("Formbricks API key is not configured. Please set it in the admin interface.")

        self.api_host = config.api_host.rstrip('/')
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        """
        Make a request to the Formbricks API.

        Args:
            endpoint: The API endpoint to call (without the base URL)
            method: HTTP method (GET, POST, etc.)
            data: Optional data to send with the request

        Returns:
            The JSON response from the API
        """
        # Ensure the endpoint has the v1 prefix
        if not endpoint.startswith("v1/"):
            endpoint = f"v1/{endpoint}"

        url = f"{self.api_host}/api/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self.headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to Formbricks API: {e}")
            raise

    def _make_request_v2(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        """
        Make a request to the Formbricks API V2.

        Args:
            endpoint: The API endpoint to call (without the base URL)
            method: HTTP method (GET, POST, etc.)
            data: Optional data to send with the request

        Returns:
            The JSON response from the API
        """
        # Ensure the endpoint has the v2 prefix
        if not endpoint.startswith("v2/"):
            endpoint = f"v2/{endpoint}"

        url = f"{self.api_host}/api/{endpoint.lstrip('/')}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self.headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to Formbricks API V2: {e}")
            raise

    def get_environments(self) -> List[Dict]:
        """
        Get all environments.

        Note: This method attempts to get environments using the V1 API.
        If the endpoint is not supported, it will return an empty list.
        Use get_surveys() instead if you need to access survey data directly.

        Returns:
            A list of environment objects (empty list if the endpoint is not supported)
        """
        try:
            response = self._make_request("environments")
            return response.get("data", [])
        except requests.exceptions.RequestException:
            logger.warning("Could not get environments. The API endpoint may not be supported in V1.")
            return []

    def get_surveys(self, environment_id: Optional[str] = None) -> List[Dict]:
        """
        Get all surveys (forms) for a specific environment or all environments using the V1 API.

        Args:
            environment_id: Optional environment ID to filter surveys

        Returns:
            A list of survey objects
        """
        try:
            # Get all surveys directly from the V2 API
            response = self._make_request("surveys")
            surveys = response.get("data", [])

            # Filter by environment_id if provided
            if environment_id:
                surveys = [s for s in surveys if s.get("environmentId") == environment_id]

            return surveys
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting surveys from V1 API: {e}")
            return []

    def get_survey_responses(self, survey_id: str, environment_id: Optional[str] = None) -> List[Dict]:
        """
        Get all responses for a specific survey using the V1 API.

        Args:
            survey_id: The survey ID
            environment_id: Optional environment ID (not used in V1 API, kept for backward compatibility)

        Returns:
            A list of response objects
        """
        try:
            # The V1 API uses a query parameter to filter responses by survey ID
            response = self._make_request(f"responses?surveyId={survey_id}")
            return response.get("data", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting survey responses from V1 API: {e}")
            return []

    def get_all_forms(self) -> List[Dict]:
        """
        Get all available forms (surveys) across all environments using the V1 API.

        Returns:
            A list of form objects with environment information
        """
        # With the V1 API, we can get all surveys directly
        surveys = self.get_surveys()

        # Convert surveys to forms format for backward compatibility
        forms = []
        for survey in surveys:
            env_id = survey.get("environmentId")
            forms.append({
                "id": survey.get("id"),
                "name": survey.get("name"),
                "environmentId": env_id,
                "environmentName": "Unknown",  # V1 API doesn't provide environment names directly
                "status": survey.get("status"),
                "createdAt": survey.get("createdAt"),
                "updatedAt": survey.get("updatedAt")
            })

        return forms

    def get_all_responses(self) -> Dict[str, List[Dict]]:
        """
        Get all responses for all forms using the V1 API.

        Returns:
            A dictionary mapping form IDs to lists of responses
        """
        forms = self.get_all_forms()
        responses = {}

        for form in forms:
            form_id = form.get("id")

            if form_id:
                form_responses = self.get_survey_responses(form_id)
                responses[form_id] = form_responses

        return responses

    def create_contact_attribute(self, environment_id: str, key: str, name: str = "Key", description: str = "The key of the user") -> Dict:
        """
        Create a user (contact attribute key) using the V2 API.

        Args:
            environment_id: The environment ID
            email: The email address to use as the key
            name: The name of the attribute (default: "Email Address")
            description: The description of the attribute (default: "The user's email address")

        Returns:
            The created contact attribute key object
        """

        data = {
            "key": key,
            "name": name,
            "description": description,
            "environmentId": environment_id
        }

        try:
            response = self._make_request_v2("management/contact-attribute-keys", method="POST", data=data)
            return response.get("data", {})
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating user with V2 API: {e}")
            raise e

# Example usage:
# api = FormbricksAPI()
# forms = api.get_all_forms()
# responses = api.get_all_responses()
# user = api.create_user("environment_id", "user@example.com")
