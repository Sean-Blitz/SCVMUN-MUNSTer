from fastapi import FastAPI

app = FastAPI()

@app.post("/auth/register")
def register_user(username: str, password: str):
    """
    Register a new user with the provided username and password. If they are not already registered.
    Also create a session token for the user and return it in the response. The session token can be used to authenticate future requests.
    """
    pass

@app.post("/auth/login")
def login_user(username: str, password: str):
    """
    Authenticate a user with the provided username and password. If they are registered, return a session token in the response. The session token can be used to authenticate future requests.
    """
    pass