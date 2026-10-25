from contract.live import Frame, PresentPerson, Who, arrival_text, parse_client, who_text
from tests.helpers import PNG_1x1, b64


def P(name, relationship):
    return PresentPerson(person_id=1, name=name, relationship=relationship, small_context="")


def test_who_text_two_people():
    assert who_text([P("David", "grandson"), P("Maria", "daughter")]) == \
        "That's David, your grandson, and Maria, your daughter."


def test_who_text_three_people():
    assert who_text([P("A", "son"), P("B", "niece"), P("C", "friend")]) == \
        "That's A, your son, B, your niece, and C, your friend."


def test_who_text_nobody():
    assert who_text([]) == "I don't see anyone I know right now."


def test_arrival_text_introduces_rather_than_corrects():
    assert arrival_text(P("David", "grandson")) == "Here's David, your grandson."


def test_parse_client_roundtrip():
    assert parse_client('{"type":"who"}') == Who()


def test_mock_live_first_frame_announces_once(client):
    with client.websocket_connect("/live") as ws:
        ws.send_text(Frame(ts=1, jpeg=b64(PNG_1x1)).model_dump_json())
        msgs = [ws.receive_json(), ws.receive_json()]
        assert {m["type"] for m in msgs} == {"present", "arrived"}
        assert next(m for m in msgs if m["type"] == "arrived")["text"].startswith("Here's ")
        ws.send_text(Frame(ts=2, jpeg=b64(PNG_1x1)).model_dump_json())
        assert ws.receive_json()["type"] == "present"


def test_mock_live_bad_message_keeps_socket_open(client):   # Review Focus 5
    with client.websocket_connect("/live") as ws:
        ws.send_text('{"type":"dance"}')
        assert ws.receive_json()["type"] == "error"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["type"] == "who_answer"


def test_mock_live_binary_message_keeps_socket_open(client):
    with client.websocket_connect("/live") as ws:
        ws.send_bytes(b"\xff\xd8 raw camera bytes")
        assert ws.receive_json()["type"] == "error"
        ws.send_text('{"type":"who"}')
        assert ws.receive_json()["type"] == "who_answer"
