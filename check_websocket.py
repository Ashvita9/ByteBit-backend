import websocket
import json
import threading
import time

def on_message(ws, message):
    data = json.loads(message)
    print(f"Received: {data}")
    if data.get('type') == 'game_over':
        print("Game Over received! Test Passed.")
        ws.close()

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Connection closed")

def on_open(ws):
    print("Connection opened")
    # Simulate code submission
    data = json.dumps({
        'type': 'code_submit',
        'code': 'print("Hello World")',
        'task_id': '123'
    })
    ws.send(data)
    print(f"Sent: {data}")

if __name__ == "__main__":
    websocket.enableTrace(True)
    ws = websocket.WebSocketApp("ws://localhost:8000/ws/battle/test_room/",
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)

    ws.run_forever()
