import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app
from routes.models import User, Location, Gender, Status

INDEX_NAME = "users"

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_es = MagicMock()
        app.dependency_overrides[lambda: app.state.es] = lambda: self.mock_es
        
        self.existing_users = {
            "1": {
                "name": "John Doe",
                "gender": "male",
                "status": "single",
                "interested_in": "female",
                "following": [2],
                "x": -122.4194,
                "y": 37.7749,
                "hobbies": ["reading", "hiking"]
            },
            "2": {
                "name": "Jane Smith",
                "gender": "female",
                "status": "single",
                "interested_in": "male",
                "following": [],
                "x": -122.4195,
                "y": 37.7748,
                "hobbies": ["hiking", "swimming"]
            },
            "3": {
                "name": "Alice Brown",
                "gender": "female",
                "status": "single",
                "interested_in": "male",
                "following": [],
                "x": -122.42,
                "y": 37.77,
                "hobbies": ["reading", "hiking", "cooking"]
            }
        }
        
        def exists_side_effect(index, id):
            return index == INDEX_NAME and id in self.existing_users
        
        self.mock_es.exists.side_effect = exists_side_effect

    def test_get_user(self):
        self.mock_es.get.return_value = {"_source": self.existing_users["1"], "_id": "1"}
        response = self.client.get("/users/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": 1,
            "name": "John Doe",
            "gender": "male",
            "status": "single",
            "interested_in": "female",
            "following": [2],
            "location": {"lon": -122.4194, "lat": 37.7749},
            "hobbies": ["reading", "hiking"]
        })

    def test_get_user_not_found(self):
        self.mock_es.exists.return_value = False
        response = self.client.get("/users/999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "User not found"})

    def test_create_user(self):
        user_data = {
            "id": 4,
            "name": "Bob Wilson",
            "gender": "male",
            "status": "single",
            "interested_in": "female",
            "following": [],
            "location": {"lon": -122.43, "lat": 37.76},
            "hobbies": ["gaming"]
        }
        self.mock_es.exists.return_value = False
        self.mock_es.index.return_value = {"result": "created"}
        response = self.client.post("/users/", json=user_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), user_data)

    def test_update_user(self):
        self.mock_es.get.return_value = {"_source": self.existing_users["1"], "_id": "1"}
        self.mock_es.index.return_value = {"result": "updated"}
        update_data = {"name": "John Updated"}
        response = self.client.patch("/users/1", json=update_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "John Updated")

    def test_get_all(self):
        self.mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": "1", "_source": self.existing_users["1"]},
                    {"_id": "2", "_source": self.existing_users["2"]},
                    {"_id": "3", "_source": self.existing_users["3"]}
                ]
            }
        }
        response = self.client.get("/users/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)
        self.assertEqual(response.json()[0]["id"], 1)

    def test_get_matches(self):
        self.mock_es.get.return_value = {"_source": self.existing_users["1"], "_id": "1"}
        self.mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": "2", "_source": self.existing_users["2"]},
                    {"_id": "3", "_source": self.existing_users["3"]}
                ]
            }
        }
        response = self.client.get("/users/1/matches")
        self.assertEqual(response.status_code, 200)
        matches = response.json()
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["id"], 3)  # 2 common hobbies, closer
        self.assertEqual(matches[1]["id"], 2)  # 1 common hobby

    def test_get_matches_not_single(self):
        self.mock_es.get.return_value = {
            "_source": {**self.existing_users["1"], "status": "married"},
            "_id": "1"
        }
        response = self.client.get("/users/1/matches")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_matches_not_found(self):
        self.mock_es.exists.return_value = False
        response = self.client.get("/users/999/matches")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "User not found"})

if __name__ == "__main__":
    unittest.main()
