# api.py
from typing import Literal
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, ModelSchema, NinjaAPI, Schema

""" 
for special events the registration is not handled by event system itself but by external applications 
this api contains the endpoints to trigger the registration flow
also the api's contains the capability to enable external attencance control (eg apps)
"""

api = NinjaAPI()

# A plain Schema until it gets its model: a ModelSchema without a Meta is
# refused at import time, which stopped the whole site from starting.
class BasePageSchema(Schema):
    pass

@api.get("/registration/", response=list[BasePageSchema])
def list_registrations(request: "HttpRequest"):
    pass
