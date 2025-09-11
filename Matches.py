from fastapi import APIRouter, HTTPException
from elasticsearch.exceptions import NotFoundError
from typing import List
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
        user_hobbies = user_doc.get("hobbies", [])

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

        sort = [
            {
                "_script": {
                    "type": "number",
                    "script": {
                        "lang": "painless",
                        "source": """
                            def user_hobbies = params.user_hobbies;
                            def doc_hobbies = doc['hobbies'];
                            int common = 0;
                            for (hobby in user_hobbies) {
                                if (doc_hobbies.contains(hobby)) {
                                    common++;
                                }
                            }
                            return common;
                        """,
                        "params": {"user_hobbies": user_hobbies}
                    },
                    "order": "desc"
                }
            },
            {
                "_geo_distance": {
                    "location": {"lat": user_location[1], "lon": user_location[0]},
                    "order": "asc",
                    "unit": "km"
                }
            }
        ]

        res = es.search(index=INDEX_NAME, body={"query": query, "sort": sort}, size=10000)
        
        matches = []
        for hit in res["hits"]["hits"]:
            source = hit["_source"]
            if "x" in source and "y" in source:
                source["location"] = {"lon": source["x"], "lat": source["y"]}
            else:
                source["location"] = {"lon": 0, "lat": 0}
            matches.append(User(id=int(hit["_id"]), **source))
        
        return matches
    except NotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve matches: {str(e)}")
