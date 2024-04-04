from fastapi import FastAPI
from router.repositories.orm import ProjectORMRepository
import json

app = FastAPI()


@app.get('/message')
def message():
    projects = ProjectORMRepository().get_all()
    return {"projects": projects}

@app.post('/message')
def message():
    projects = ProjectORMRepository().get_all()
    return {"projects": projects}
