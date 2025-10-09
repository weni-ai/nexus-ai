from dataclasses import dataclass

import requests


def found_cep(cep: str):
    return requests.get(f"https://viacep.com.br/ws/{cep}/json/").json()


@dataclass
class Product:
    name: str
    preco: str
    quantidade: int


def found_products(name):

    return []


registry = {"found_cep": found_cep, "found_products": found_products}
