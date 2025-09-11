from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
from math import radians, sin, cos, sqrt, atan2
from ..models import User
from ..db import es, INDEX_NAME

router = APIRouter()

@router.get(path="/users/{id}/matches", response_model=List[User])
def get_matches(id: int):
    try:
        if not es.exists(index=INDEX_NAME, id=str(id)):
            raise HTTPException(status_code=404, detail="User not found")
        
        user_doc = es.get(index=INDEX_NAME, id=str(id))["_source"]
        user_status = user_doc.get("status")
        user_location = [user_doc.get("x", 0), user_doc.get("y", 0)]
        user_hobbies = set(user_doc.get("hobbies", []))

        if user_status != "single":
            return []

        query = {
            "bool": {
                "filter": [
                    {"term": {"status": "single"}},
                    {"bool": {"must_not": {"term": {"_id": str(id)}}}}
                ]
            }
        }

        res = es.search(index=INDEX_NAME, body={"query": query}, size=10000)
        
        matches = []
        for hit in res["hits"]["hits"]:
            source = hit["_source"]
            match_id = int(hit["_id"])
            match_hobbies = set(source.get("hobbies", []))
            common_hobbies = len(user_hobbies.intersection(match_hobbies))
            
            match_location = [source.get("x", 0), source.get("y", 0)]
            distance = calculate_distance(user_location[1], user_location[0], match_location[1], match_location[0])
            
            if "x" in source and "y" in source:
                source["location"] = {"lon": source["x"], "lat": source["y"]}
            else:
                source["location"] = {"lon": 0, "lat": 0}
                
            matches.append({
                "user": User(id=match_id, **source),
                "common_hobbies": common_hobbies,
                "distance": distance
            })
        
        matches.sort(key=lambda x: (-x["common_hobbies"], x["distance"]))
        return [match["user"] for match in matches]
    
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve matches: {str(e)}")

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
