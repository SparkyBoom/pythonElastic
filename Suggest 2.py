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
        user_status = user_doc.get("status")
        user_following = user_doc.get("following", [])
        
        if user_status != "single":
            return []
        
        suggested_ids = set()
        for followed_id in user_following:
            if es.exists(index=INDEX_NAME, id=str(followed_id)):
                followed_doc = es.get(index=INDEX_NAME, id=str(followed_id))["_source"]
                followed_following = followed_doc.get("following", [])
                suggested_ids.update(followed_following)
        
        suggested_ids.discard(id)
        for fid in user_following:
            suggested_ids.discard(fid)
        
        suggestions = []
        for sid in suggested_ids:
            if es.exists(index=INDEX_NAME, id=str(sid)):
                doc = es.get(index=INDEX_NAME, id=str(sid))["_source"]
                if doc.get("status") == "single":
                    if "location" in doc and isinstance(doc["location"], list):
                        doc["location"] = {"lon": doc["location"][0], "lat": doc["location"][1]}
                    suggestions.append(
                        User(
                            id=sid,
                            name=doc["name"],
                            gender=doc["gender"],
                            status=doc["status"],
                            interested_in=doc.get("interested_in"),
                            following=[],
                            location=doc["location"]
                        )
                    )
        
        return suggestions
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
