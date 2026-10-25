"""The patient's laptop at visit time: `python -m live`.

Opens the webcam and names the faces it knows, listens to the microphone and names the voices it
knows, both from the same `people` rows in Postgres. It announces arrivals out loud, keeps the
visit's transcript, has Gemini turn it into facts and a fresh card for each visitor when the visit
ends, and answers "Nova, who is David?" from the database.
"""
