# LLM Event Importer

This module provides functionality to import events from natural language text using OpenAI's GPT-4o-mini model (equivalent to GPT 4.1 nano). It can process both plain text and HTML inputs to extract structured event data and create Event objects in the database.

## Features

- Extract event information from natural language text
- Process both plain text and HTML inputs
- Validate extracted data to avoid hallucinations
- Create Event objects with appropriate tags, addresses, and descriptions
- Double-check extracted information for consistency and accuracy

## Requirements

- Python 3.8+
- Django
- OpenAI Python client
- html2text package

Install the required packages:

```bash
pip install openai html2text
```

## Setup

1. Set your OpenAI API key as an environment variable:

```bash
export OPENAI_API_KEY=your_api_key_here
```

Alternatively, you can pass the API key directly when calling the import function.

## Usage

### Basic Usage

```python
from Administration.importers.LLM_import import import_event_from_text

# Import an event from plain text
text = """
Concert de Jazz au Café des Arts
Le groupe "Les Improvisateurs" se produira le 15 juin 2023 à 20h30 au Café des Arts.
Adresse: 15 rue de la Musique, 34000 Montpellier, France.
Venez découvrir ce trio de jazz qui revisite les standards avec une touche de modernité.
Le concert se terminera vers 23h. Entrée: 10€.
"""

success, result = import_event_from_text(text)

if success:
    print(f"Event created: {result.name}")
else:
    print(f"Error: {result}")
```

### HTML Input

The importer can also process HTML input:

```python
html = """
<h1>Concert de Jazz au Café des Arts</h1>
<p>Le groupe "Les Improvisateurs" se produira le <strong>15 juin 2023 à 20h30</strong> au Café des Arts.</p>
<p>Adresse: <em>15 rue de la Musique, 34000 Montpellier, France</em>.</p>
<p>Venez découvrir ce trio de jazz qui revisite les standards avec une touche de modernité.</p>
<p>Le concert se terminera vers 23h. Entrée: 10€.</p>
"""

success, result = import_event_from_text(html)
```

### Specifying API Key

If you don't want to use the environment variable, you can pass the API key directly:

```python
success, result = import_event_from_text(text, api_key="your_api_key_here")
```

## How It Works

1. **Preprocessing**: The input text is preprocessed, converting HTML to plain text if needed.
2. **Extraction**: The LLM extracts structured event data from the preprocessed text.
3. **Validation**: A second LLM call validates the extracted data to check for hallucinations.
4. **Creation**: The validated data is used to create an Event object with appropriate tags and address.

## Testing

A test script is provided to verify the functionality:

```bash
python Administration/importers/test_llm_import.py
```

## Extracted Data

The LLM extracts the following information:
- Event name
- Start date and time
- End date and time (if available)
- Venue name
- Address
- Short and long descriptions
- Tags/categories
- Event type (concert, festival, etc.)

## Error Handling

The importer includes robust error handling to deal with:
- Invalid input text
- LLM API errors
- JSON parsing errors
- Invalid date formats
- Missing required fields

If an error occurs, the import_event_from_text function returns (False, error_message).