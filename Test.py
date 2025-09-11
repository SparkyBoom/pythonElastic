// test_api.py
import unittest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app  # Import the FastAPI app

client = TestClient(app)

# Mock Elasticsearch to avoid real connections
@patch('db.es')
class TestCreateUser(unittest.TestCase):
    def setUp(self):
        self.user_data = {
            "id": 1,
            "name": "John Doe",
            "gender": "male",
            "status": "single",
            "interested_in": "female",
            "following": [2],
            "location": {"lon": -122.4194, "lat": 37.7749}
        }

    def test_create_user_success(self, mock_es):
        mock_es.exists.return_value = False
        mock_es.index.return_value = {"result": "created"}

        response = client.post("/users/", json=self.user_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], 1)
        mock_es.index.assert_called_once()

    def test_create_user_missing_id(self, mock_es):
        del self.user_data["id"]
        response = client.post("/users/", json=self.user_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("User ID is required", response.json()["detail"])

    def test_create_user_already_exists(self, mock_es):
        mock_es.exists.return_value = True
        response = client.post("/users/", json=self.user_data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("User with this ID already exists", response.json()["detail"])

-------------
@patch('db.es')
class TestGetUser(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.user_data = {
            "name": "John Doe",
            "gender": "male",
            "status": "single",
            "interested_in": "female",
            "following": [2],
            "location": [-122.4194, 37.7749]  # ES format
        }

    def test_get_user_success(self, mock_es):
        mock_es.get.return_value = {"_source": self.user_data}

        response = client.get(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "John Doe")
        self.assertIn("location", response.json())

    def test_get_user_not_found(self, mock_es):
        mock_es.get.side_effect = Exception("Not Found")  # Simulate NotFoundError

        response = client.get(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_get_user_error(self, mock_es):
        mock_es.get.side_effect = Exception("Connection error")

        response = client.get(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Connection error", response.json()["detail"])

-------------
@patch('db.es')
class TestUpdateUser(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.update_data = {"name": "Jane Doe"}

    def test_update_user_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.update.return_value = {"result": "updated"}
        mock_es.get.return_value = {"_source": {"name": "Jane Doe", "location": [-122.4194, 37.7749]}}

        response = client.patch(f"/users/{self.user_id}", json=self.update_data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Jane Doe")

    def test_update_user_not_found(self, mock_es):
        mock_es.exists.return_value = False

        response = client.patch(f"/users/{self.user_id}", json=self.update_data)
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_update_user_no_fields(self, mock_es):
        response = client.patch(f"/users/{self.user_id}", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("No fields provided for update", response.json()["detail"])

    def test_update_user_location(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.update.return_value = {"result": "updated"}
        update_with_location = {"location": {"lon": -122.42, "lat": 37.77}}
        mock_es.get.return_value = {"_source": {"location": [-122.42, 37.77]}}

        response = client.patch(f"/users/{self.user_id}", json=update_with_location)
        self.assertEqual(response.status_code, 200)

-------------
@patch('db.es')
class TestDeleteUser(unittest.TestCase):
    def setUp(self):
        self.user_id = 1

    def test_delete_user_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.delete.return_value = {"result": "deleted"}

        response = client.delete(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 204)

    def test_delete_user_not_found(self, mock_es):
        mock_es.exists.return_value = False

        response = client.delete(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_delete_user_error(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.delete.return_value = {"result": "error"}

        response = client.delete(f"/users/{self.user_id}")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to delete user", response.json()["detail"])

-------------
@patch('db.es')
class TestSuggestions(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.user_doc = {"following": [2]}

    def test_get_suggestions_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.get.side_effect = lambda *args, **kwargs: {"_source": {"following": [3]}} if "2" in args[1] else {"_source": {"name": "Suggested", "gender": "female", "status": "single", "interested_in": "male", "following": [], "location": [-122.42, 37.77]}}

        response = client.get(f"/users/{self.user_id}/suggestions")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_get_suggestions_user_not_found(self, mock_es):
        mock_es.exists.return_value = False

        response = client.get(f"/users/{self.user_id}/suggestions")
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_get_suggestions_no_suggestions(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": {"following": []}}

        response = client.get(f"/users/{self.user_id}/suggestions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

-------------
@patch('db.es')
class TestDeleteAllUsers(unittest.TestCase):
    def test_delete_all_users_success(self, mock_es):
        mock_es.delete_by_query.return_value = {"deleted": 5}

        response = client.delete("/users/")
        self.assertEqual(response.status_code, 204)

    def test_delete_all_users_error(self, mock_es):
        mock_es.delete_by_query.side_effect = Exception("Error")

        response = client.delete("/users/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to delete all users", response.json()["detail"])

-------------
@patch('db.es')
class TestGetAllUsers(unittest.TestCase):
    def setUp(self):
        self.users_data = [
            {"_id": "1", "_source": {"name": "John", "gender": "male", "status": "single", "interested_in": "female", "following": [2], "location": [-122.4194, 37.7749]}}
        ]

    def test_get_all_users_success(self, mock_es):
        mock_es.search.return_value = {"hits": {"hits": self.users_data}}

        response = client.get("/users/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["name"], "John")

    def test_get_all_users_with_filter(self, mock_es):
        mock_es.search.return_value = {"hits": {"hits": []}}
        response = client.get("/users/?gender=male&status=single")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_all_users_location_filter_invalid(self, mock_es):
        response = client.get("/users/?lon=1")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Both lon and lat must be provided", response.json()["detail"])

    def test_get_all_users_error(self, mock_es):
        mock_es.search.side_effect = Exception("Error")

        response = client.get("/users/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Error", response.json()["detail"])

-------------
@patch('db.es')
class TestGetFollowers(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.followers_data = [
            {"_id": "2", "_source": {"name": "Follower", "gender": "female", "status": "single", "interested_in": "male", "following": [1], "location": [-122.42, 37.77]}}
        ]

    def test_get_followers_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.search.return_value = {"hits": {"hits": self.followers_data}}

        response = client.get(f"/users/{self.user_id}/followers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_get_followers_no_followers(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.search.return_value = {"hits": {"hits": []}}

        response = client.get(f"/users/{self.user_id}/followers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_followers_error(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.search.side_effect = Exception("Error")

        response = client.get(f"/users/{self.user_id}/followers")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Error", response.json()["detail"])

-------------
@patch('db.es')
class TestGetFollowing(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.user_doc = {"following": [2]}
        self.following_doc = {"name": "Followed", "gender": "female", "status": "single", "interested_in": "male", "following": [], "location": [-122.42, 37.77]}

    def test_get_following_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.side_effect = [
            {"_source": self.user_doc},
            {"_source": self.following_doc}
        ]

        response = client.get(f"/users/{self.user_id}/following")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_get_following_user_not_found(self, mock_es):
        mock_es.exists.return_value = False

        response = client.get(f"/users/{self.user_id}/following")
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_get_following_no_following(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": {"following": []}}

        response = client.get(f"/users/{self.user_id}/following")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

-------------
@patch('db.es')
class TestFollow(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.follow_id = 2
        self.user_doc = {"following": []}

    def test_add_follow_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.update.return_value = {"result": "updated"}

        response = client.post(f"/users/{self.user_id}/follow/{self.follow_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("following", response.json())

    def test_add_follow_self(self, mock_es):
        response = client.post(f"/users/{self.user_id}/follow/{self.user_id}")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Cannot follow self", response.json()["detail"])

    def test_add_follow_already_following(self, mock_es):
        mock_es.exists.return_value = True
        self.user_doc["following"] = [self.follow_id]
        mock_es.get.return_value = {"_source": self.user_doc}

        response = client.post(f"/users/{self.user_id}/follow/{self.follow_id}")
        self.assertEqual(response.status_code, 200)  # No error, just no change

    def test_remove_follow_success(self, mock_es):
        mock_es.exists.return_value = True
        self.user_doc["following"] = [self.follow_id]
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.update.return_value = {"result": "updated"}

        response = client.delete(f"/users/{self.user_id}/follow/{self.follow_id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.follow_id, response.json()["following"])

    def test_remove_follow_not_following(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.update.return_value = {"result": "updated"}

        response = client.delete(f"/users/{self.user_id}/follow/{self.follow_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["following"], [])

-------------
@patch('db.es')
class TestGetMatches(unittest.TestCase):
    def setUp(self):
        self.user_id = 1
        self.user_doc = {
            "gender": "male",
            "interested_in": "female",
            "status": "single",
            "following": [2]
        }
        self.match_doc = {
            "_id": "2",
            "_source": {
                "gender": "female",
                "interested_in": "male",
                "status": "single",
                "name": "Match",
                "following": [],
                "location": [-122.42, 37.77]
            }
        }

    def test_get_matches_success(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.search.return_value = {"hits": {"hits": [self.match_doc]}}

        response = client.get(f"/users/{self.user_id}/matches")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["name"], "Match")

    def test_get_matches_user_not_single(self, mock_es):
        mock_es.exists.return_value = True
        self.user_doc["status"] = "married"
        mock_es.get.return_value = {"_source": self.user_doc}

        response = client.get(f"/users/{self.user_id}/matches")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_matches_no_matches(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.return_value = {"_source": self.user_doc}
        mock_es.search.return_value = {"hits": {"hits": []}}

        response = client.get(f"/users/{self.user_id}/matches")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_matches_user_not_found(self, mock_es):
        mock_es.exists.return_value = False

        response = client.get(f"/users/{self.user_id}/matches")
        self.assertEqual(response.status_code, 404)
        self.assertIn("User not found", response.json()["detail"])

    def test_get_matches_error(self, mock_es):
        mock_es.exists.return_value = True
        mock_es.get.side_effect = Exception("Error")

        response = client.get(f"/users/{self.user_id}/matches")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to retrieve matches", response.json()["detail"])

if __name__ == '__main__':
    unittest.main()
