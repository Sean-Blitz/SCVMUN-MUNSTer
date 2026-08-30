from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str = "Default Item"
    description: str
    price: float
    tax: float
# this is a Pydantic model that defines the structure of an item. It lets you validate data
# that comes in and goes out of your API. Name field has a default value.
# you can see below at def create_item that it accepts an Item object as input from JSON body.
# Default values do not need to be filled in by the JSON in the response body.
# Example response body: {"name": "Default Item", "description": "A sample item", "price": 10.0, "tax": 1.0}

@app.get("/")
def root():
    return {"message": "Hello, World!"}

@app.get("/items/")
def create_item(item: Item): 
    items = ["item1", "item2", "item3"]
    items.append(item.name)
    return {"items": items}
# this one, which takes item, takes data from the query string. You may call it using an example
# query like "/items/?item=NewItem" to pass NewItem into the code.
# also, any FastAPI endpoint will accept a request body (such as the Item object here).

@app.get("/items/{item_id}")
def read_item(item_id: int):
    items = ["item1", "item2", "item3"]
    if item_id < len(items):
        return {"item": items[item_id]}
    else:
        raise HTTPException(status_code=404, detail="Item not found")
# This endpoint takes an item_id as a path parameter. 
# you may call it using /items/0 or something like that.

@app.get("/with_response", response_model=Item)
def provide_response(item_id: int):
    items = ["item1", "item2", "item3"]
    if item_id < len(items):
        return {"item": items[item_id]}
    else:
        raise HTTPException(status_code=404, detail="Item not found")
# response model tells FastAPI to use the Item model to validate and serialize the response data.
# You see, this one would fail because the response model expects an Item object, but the returned dictionary does not match the structure of the Item model.
# Works great with frontend and natiively!