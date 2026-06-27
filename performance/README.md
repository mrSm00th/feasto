# Locust Load Testing

Run the benchmark with:

```bash
locust -f locustfile.py --host=http://localhost:8000
```

Then open:

```text
http://localhost:8089
```

in your browser and start the test.

Before running:

* Replace `ADD_YOUR_EMAIL` and `ADD_YOUR_PASSWORD` with valid credentials.
* Replace `RESTAURANT_ID` with a restaurant UUID that exists in your database.

The test simulates:

* Restaurant discovery
* Restaurant detail views
* Menu category browsing
* Authenticated order retrieval
