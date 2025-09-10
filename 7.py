# models.py
from pydantic import BaseModel
from enum import Enum
from typing import List, Optional

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
    lon: float
    lat: float

# Model for user data (used for input and output)
class User(BaseModel):
    id: Optional[int] = None  # Optional for suggestions, required for POST
    name: str
    gender: Gender
    status: Status
    following: List[int]
    location: Location

# Model for partial updates (PATCH)
class UserUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[Gender] = None
    status: Optional[Status] = None
    following: Optional[List[int]] = None
    location: Optional[Location] = None
--------
# db.py
from elasticsearch import Elasticsearch

# Initialize Elasticsearch client
es = Elasticsearch(hosts=["http://localhost:9200"])

# Define the index name
INDEX_NAME = "users"

# Create the index if it doesn't exist with mappings
if not es.indices.exists(index=INDEX_NAME):
    es.indices.create(
        index=INDEX_NAME,
        body={
            "mappings": {
                "properties": {
                    "name": {"type": "text"},
                    "gender": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "following": {"type": "integer"},
                    "location": {"type": "geo_point"}
                }
            }
        }
    )
--------
# routes/create_user.py
from fastapi import APIRouter, HTTPException
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.post(path="/users/", response_model=User)
def create_user(user: User):
    if user.id is None:
        raise HTTPException(status_code=400, detail="User ID is required")
    if es.exists(index=INDEX_NAME, id=str(user.id)):
        raise HTTPException(status_code=400, detail="User with this ID already exists")
    
    body = user.dict(exclude={"id"})
    body["location"] = [user.location.lon, user.location.lat]  # Store as [lon, lat] for geo_point
    res = es.index(index=INDEX_NAME, id=str(user.id), body=body)
    if res["result"] != "created":
        raise HTTPException(status_code=500, detail="Failed to create user")
    return User(id=user.id, **body)
--------
# routes/get_user.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/{id}", response_model=User)
def get_user(id: int):
    try:
        res = es.get(index=INDEX_NAME, id=str(id))
        source = res["_source"]
        if "location" in source and isinstance(source["location"], list):
            source["location"] = {"lon": source["location"][0], "lat": source["location"][1]}
        return User(id=id, **source)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/update_user.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from ..models import User, UserUpdate
from ..db import es, INDEX_NAME

router = APIRouter()

@router.patch(path="/users/{id}", response_model=User)
def update_user(id: int, user_update: UserUpdate):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        update_doc = {k: v for k, v in user_update.dict().items() if v is not None}
        if "location" in update_doc:
            update_doc["location"] = [update_doc["location"].lon, update_doc["location"].lat]
        if not update_doc:
            raise HTTPException(status_code=400, detail="No fields provided for update")
        
        res = es.update(index=INDEX_NAME, id=str(id), body={"doc": update_doc})
        if res["result"] != "updated":
            raise HTTPException(status_code=500, detail="Failed to update user")
        
        updated_doc = es.get(index=INDEX_NAME, id=str(id))
        source = updated_doc["_source"]
        if "location" in source and isinstance(source["location"], list):
            source["location"] = {"lon": source["location"][0], "lat": source["location"][1]}
        return User(id=id, **source)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/delete_user.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from ..db import es, INDEX_NAME

router = APIRouter()

@router.delete(path="/users/{id}", status_code=204)
def delete_user(id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        res = es.delete(index=INDEX_NAME, id=str(id))
        if res["result"] != "deleted":
            raise HTTPException(status_code=500, detail="Failed to delete user")
        return None
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/suggestions.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/{id}/suggestions", response_model=List[User])
def get_user_suggestions(id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        user_doc = es.get(index=INDEX_NAME, id=str(id))["_source"]
        following = user_doc.get("following", [])
        
        suggested_ids = set()
        for followed_id in following:
            if es.exists(index=INDEX_NAME, id=str(followed_id)):
                followed_doc = es.get(index=INDEX_NAME, id=str(followed_id))["_source"]
                followed_following = followed_doc.get("following", [])
                suggested_ids.update(followed_following)
        
        suggested_ids.discard(id)
        for fid in following:
            suggested_ids.discard(fid)
        
        suggestions = []
        for sid in suggested_ids:
            if es.exists(index=INDEX_NAME, id=str(sid)):
                doc = es.get(index=INDEX_NAME, id=str(sid))["_source"]
                if "location" in doc and isinstance(doc["location"], list):
                    doc["location"] = {"lon": doc["location"][0], "lat": doc["location"][1]}
                suggestions.append(
                    User(
                        id=sid,
                        name=doc["name"],
                        gender=doc["gender"],
                        status=doc["status"],
                        following=[],
                        location=doc["location"]
                    )
                )
        
        return suggestions
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/delete_all.py
from fastapi import APIRouter, HTTPException
from ..db import es, INDEX_NAME

router = APIRouter()

@router.delete(path="/users/", status_code=204)
def delete_all_users():
    try:
        res = es.delete_by_query(index=INDEX_NAME, body={"query": {"match_all": {}}})
        if res["deleted"] is None:
            raise HTTPException(status_code=500, detail="Failed to delete all users")
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/get_all.py
from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from ..models import Gender, Status, User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/", response_model=List[User])
def get_all_users(
    name: Optional[str] = Query(None),
    gender: Optional[Gender] = Query(None),
    status: Optional[Status] = Query(None),
    following: Optional[int] = Query(None),
    lon: Optional[float] = Query(None),
    lat: Optional[float] = Query(None),
    radius: Optional[float] = Query(10.0, ge=0.1)
):
    if (lon is not None and lat is None) or (lon is None and lat is not None):
        raise HTTPException(status_code=400, detail="Both lon and lat must be provided for location filtering")
    
    query = {"bool": {"filter": []}}
    if name:
        query["bool"]["filter"].append({"match": {"name": name}})
    if gender:
        query["bool"]["filter"].append({"term": {"gender": gender.value}})
    if status:
        query["bool"]["filter"].append({"term": {"status": status.value}})
    if following is not None:
        query["bool"]["filter"].append({"term": {"following": following}})
    if lon is not None and lat is not None:
        query["bool"]["filter"].append({
            "geo_distance": {
                "distance": f"{radius}km",
                "location": {"lon": lon, "lat": lat}
            }
        })
    if not query["bool"]["filter"]:
        query = {"match_all": {}}
    
    try:
        res = es.search(index=INDEX_NAME, body={"query": query}, size=10000)
        users = []
        for hit in res["hits"]["hits"]:
            source = hit["_source"]
            if "location" in source and isinstance(source["location"], list):
                source["location"] = {"lon": source["location"][0], "lat": source["location"][1]}
            users.append(User(id=int(hit["_id"]), **source))
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/get_followers.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/{id}/followers", response_model=List[User])
def get_followers(id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        query = {"term": {"following": id}}
        res = es.search(index=INDEX_NAME, body={"query": query}, size=10000)
        users = []
        for hit in res["hits"]["hits"]:
            source = hit["_source"]
            if "location" in source and isinstance(source["location"], list):
                source["location"] = {"lon": source["location"][0], "lat": source["location"][1]}
            users.append(User(id=int(hit["_id"]), **source))
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/get_following.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/{id}/following", response_model=List[User])
def get_following(id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        user_doc = es.get(index=INDEX_NAME, id=str(id))["_source"]
        following = user_doc.get("following", [])
        
        following_users = []
        for follow_id in following:
            if es.exists(index=INDEX_NAME, id=str(follow_id)):
                doc = es.get(index=INDEX_NAME, id=str(follow_id))["_source"]
                if "location" in doc and isinstance(doc["location"], list):
                    doc["location"] = {"lon": doc["location"][0], "lat": doc["location"][1]}
                following_users.append(User(id=follow_id, **doc))
        
        return following_users
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# routes/follow.py
from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
from ..db import es, INDEX_NAME

router = APIRouter()

@router.post(path="/users/{id}/follow/{follow_id}", response_model=dict)
def add_follow(id: int, follow_id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        if not es.exists(index=INDEX_NAME, id=str(follow_id)):
            raise HTTPException(status_code=404, detail="Follow user not found")
        if id == follow_id:
            raise HTTPException(status_code=400, detail="Cannot follow self")
        
        user_doc = es.get(index=INDEX_NAME, id=str(id))["_source"]
        if follow_id not in user_doc.get("following", []):
            user_doc["following"].append(follow_id)
            es.update(index=INDEX_NAME, id=str(id), body={"doc": {"following": user_doc["following"]}})
        
        return {"id": id, "following": user_doc["following"]}
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(path="/users/{id}/follow/{follow_id}", response_model=dict)
def remove_follow(id: int, follow_id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        if not es.exists(index=INDEX_NAME, id=str(follow_id)):
            raise HTTPException(status_code=404, detail="Follow user not found")
        
        user_doc = es.get(index=INDEX_NAME, id=str(id))["_source"]
        user_doc["following"] = [f for f in user_doc.get("following", []) if f != follow_id]
        es.update(index=INDEX_NAME, id=str(id), body={"doc": {"following": user_doc["following"]}})
        
        return {"id": id, "following": user_doc["following"]}
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
--------
# main.py
from fastapi import FastAPI
from routes.create_user import router as create_router
from routes.get_user import router as get_router
from routes.update_user import router as update_router
from routes.delete_user import router as delete_router
from routes.suggestions import router as suggestions_router
from routes.delete_all import router as delete_all_router
from routes.get_all import router as get_all_router
from routes.get_followers import router as get_followers_router
from routes.get_following import router as get_following_router
from routes.follow import router as follow_router

app = FastAPI()

# Include all routers
app.include_router(create_router)
app.include_router(get_router)
app.include_router(update_router)
app.include_router(delete_router)
app.include_router(suggestions_router)
app.include_router(delete_all_router)
app.include_router(get_all_router)
app.include_router(get_followers_router)
app.include_router(get_following_router)
app.include_router(follow_router)
