import requests

url = "https://public-api.luma.com/v1/event/get"

headers = {"accept": "application/json"}

response = requests.get(url, headers=headers)

print(response.text)

import requests

url = "https://public-api.luma.com/v1/event/get-guest"

headers = {"accept": "application/json"}

response = requests.get(url, headers=headers)

print(response.text)

import requests

url = "https://public-api.luma.com/v1/event/get-guests"

headers = {"accept": "application/json"}

response = requests.get(url, headers=headers)

print(response.text)

import requests

url = "https://public-api.luma.com/v1/event/add-guests"

headers = {
    "accept": "application/json",
    "content-type": "application/json"
}

response = requests.post(url, headers=headers)

print(response.text)