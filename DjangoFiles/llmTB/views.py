from django.shortcuts import render

from BaseBillet.models import Product
from Customers.models import Client

from langchain.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI

from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, validator
from typing import List

# Create your views here.


def ask_llm(request):
    if request.method == 'GET':
        model_name = "text-davinci-003"
        temperature = 0.0
        model = OpenAI(model_name=model_name, temperature=temperature)

        prompt = """
        Tu es un assistant qui fabrique des dictionnaire python de ce type : 
         
        nouvel_evenement = {
          name:str
          datetime: datetime
          lieux : uuid
          artists: uuid
          products: uuid
          options : uuid
          tags: uuid
          short_description: str
        }
        
        Avec l'aide du contexte fourni, construit un dictionnaire qui contient toutes les informations nécessaires à la création de cet évènement :
        
        Un concert de Ziskakan le deuxieme vendredi de janvier 2024 à 20h30 à la salle de spectacle "Le Bisik". 
        Billet d'entrée avec deux tarif :  5€ pour les adhérants de l'association et 10€ en plein tarif
        """
        print(prompt)
        pass
