from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from typing import List, Optional

app = FastAPI()

# Initialize Elasticsearch client (assumes running locally on default port)
es = Elasticsearch(hosts=["http://localhost:9200"])

# Define the index name
INDEX_NAME = "users"

# Create the index if it doesn't exist with mappings for better type control
if not es.indices.exists(index=INDEX_NAME):
    es.indices.create(
        index=INDEX_NAME,
        body={
            "mappings": {
                "properties": {
                    "gender": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "following": {"type": "integer"},
                    "location": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "float"},
                            "y": {"type": "float"}
                        }
                    }
                }
            }
        }
    )

# Enum for gender
class Gender(Enum):
    male = "male"
    female = "female"

# Enum for marital status
class Status(Enum):
    married = "married"
    single = "single"

# Model for location
class Location(BaseModel):
    x: float
    y: float

# Base model for user data
class User(BaseModel):
    gender: Gender
    status: Status
    following: List[int]
    location: Location

# Model for user input (with ID)
class UserIn(User):
    id: int

# Model for user output (with ID)
class UserOut(User):
    id: int

# Model for partial updates (PATCH)
class UserUpdate(BaseModel):
    gender: Optional[Gender] = None
    status: Optional[Status] = None
    following: Optional[List[int]] = None
    location: Optional[Location] = None

# Model for suggestions output
class UserSuggestion(BaseModel):
    id: int
    gender: Gender
    status: Status
    location: Location

# POST: Create a new user
@app.post("/users/", response_model=UserOut)
def create_user(user: UserIn):
    if es.exists(index=INDEX_NAME, id=str(user.id)):
        raise HTTPException(status_code=400, detail="User with this ID already exists")
    
    body = user.dict(exclude={"id"})
    res = es.index(index=INDEX_NAME, id=str(user.id), body=body)
    if res["result"] != "created":
        raise HTTPException(status_code=500, detail="Failed to create user")
    return UserOut(id=user.id, **body)

# GET: Retrieve a user by ID
@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int):
    try:
        res = es.get(index=INDEX_NAME, id=str(user_id))
        return UserOut(id=user_id, **res["_source"])
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# PATCH: Update a user's fields
@app.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, user_update: UserUpdate):
    try:
        if not es.exists(index=INDEX_NAME, id=str(user_id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        update_body = {
            "doc": {k: v for k, v in user_update.dict().items() if v is not None}
        }
        if not update_body["doc"]:
            raise HTTPException(status_code=400, detail="No fields provided for update")
        
        res = es.update(index=INDEX_NAME, id=str(user_id), body=update_body)
        if res["result"] != "updated":
            raise HTTPException(status_code=500, detail="Failed to update user")
        
        updated_doc = es.get(index=INDEX_NAME, id=str(user_id))
        return UserOut(id=user_id, **updated_doc["_source"])
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# DELETE: Delete a user by ID
@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(user_id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        res = es.delete(index=INDEX_NAME, id=str(user_id))
        if res["result"] != "deleted":
            raise HTTPException(status_code=500, detail="Failed to delete user")
        return None
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GET: Suggest users based on "friends of friends"
@app.get("/users/{user_id}/suggestions", response_model=List[UserSuggestion])
def get_user_suggestions(user_id: int):
    try:
        # Step 1: Get the target user's following list
        if not es.exists(index=INDEX_NAME, id=str(user_id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        user_doc = es.get(index=INDEX_NAME, id=str(user_id))["_source"]
        following = user_doc.get("following", [])
        
        # Step 2: Collect users followed by the users in the following list
        suggested_ids = set()
        for followed_id in following:
            if es.exists(index=INDEX_NAME, id=str(followed_id)):
                followed_doc = es.get(index=INDEX_NAME, id=str(followed_id))["_source"]
                followed_following = followed_doc.get("following", [])
                suggested_ids.update(followed_following)
        
        # Step 3: Exclude users already followed and the target user
        suggested_ids.discard(user_id)
        for fid in following:
            suggested_ids.discard(fid)
        
        # Step 4: Retrieve details for suggested users
        suggestions = []
        for sid in suggested_ids:
            if es.exists(index=INDEX_NAME, id=str(sid)):
                doc = es.get(index=INDEX_NAME, id=str(sid))["_source"]
                suggestions.append(
                    UserSuggestion(
                        id=sid,
                        gender=doc["gender"],
                        status=doc["status"],
                        location=doc["location"]
                    )
                )
        
        return suggestions
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
