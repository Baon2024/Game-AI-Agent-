import websockets
import asyncio
import json
import requests
import sys
from pathlib import Path
import uuid
from gameAIAgent.interactiveAgent.agent import Agent
import traceback

games = {}
tool_call_responses = {}
## use this to save asyncio.Future(), with agent's id, so agent pauses untiul tool function is returned from frontend




system_prompt = """You are a tic-tac-toe playing agent, playing against a human. After each human turn, you will be send the state of the game board,
and then you must choose your move

"""

async def run_agent_turn(ws, agent, game_id, new_game_state):
      print(f"[ws] starting agent turn game_id={game_id}")
      agent_turn_result = await agent.generate_response(new_game_state)
      print(f"[ws] agent turn result game_id={game_id} result={agent_turn_result}")

      if agent_turn_result.get("turn_successful"):
          await ws.send(json.dumps({"message_type": "human_turn_start"}))
      else:
          await ws.send(json.dumps({
              "message_type": "agent_turn_failed",
              "reason": agent_turn_result.get("reason"),
              "game_id": game_id,
          }))



## have websocket server here
async def handler(ws):
    global tool_call_responses
    global current_ws
    current_ws = ws


    try:
        async for message in ws:
            print(f"[ws] raw message received: {message}")
            contents = json.loads(message)
            print(f"[ws] parsed message_type={contents.get('message_type')} contents={contents}")

            match contents["message_type"]:
                case "new_game":
                    new_game_id = contents.get("new_game_id")
                    print(f"[ws] new_game requested new_game_id={new_game_id}")
                    if not new_game_id:
                        print("[ws] new_game failed: missing_new_game_id")
                        await ws.send(json.dumps({
                            "message_type": "new_game_failed",
                            "reason": "missing_new_game_id",
                        }))
                        continue
                    
                    ## use tool_schema sent from frontend
                    tools_schema = contents.get("tools_schema", None)
                    print(f"[ws] new_game tools_schema_count={len(tools_schema) if tools_schema is not None else 'None'} tools_schema={tools_schema}")
                    if tools_schema is None:
                        print("No tools schema was provided to games agent - ending game set-up..")
                        sys.exit(1)

                    ## system prompt here needs to inform agent that it can only choose one tool call at a time - any more won't be executed
                    games[f"{new_game_id}"] = Agent(game_id=new_game_id, system_prompt=system_prompt, execute_tool_call_ws=ws, tool_call_results_queue=tool_call_responses, tools_schema=tools_schema, llm_provider="Cerebras")
                    print(f"[ws] new_game created game_id={new_game_id}; active_games={list(games.keys())}")
                    ## just hamdle passing updates for tool calls, by making tool_call_responses passed to new agent
                
                case "tool_call_response":
                    tool_call_id = contents["tool_call_id"]
                    print(f"[ws] tool_call_response received tool_call_id={tool_call_id} result={contents.get('tool_call_result')}")
                    response = tool_call_responses.get(tool_call_id)
                    if response is None:
                        print(f"[ws] no pending future for tool_call_id={tool_call_id}; pending_ids={list(tool_call_responses.keys())}")
                        continue ## if it's somehow been completed alreadu
                    if not response.done():
                        print(f"[ws] resolving future for tool_call_id={tool_call_id}")
                        response.set_result(contents["tool_call_result"])
                    else:
                        print(f"[ws] future already resolved for tool_call_id={tool_call_id}")
                    tool_call_responses.pop(tool_call_id, None)
                        # that should handle the agent getting it's result back automatically
                
                

                case "update_game_state_and_agent_move":
                    game_id = contents["game_id"]
                    print(f"[ws] update_game_state_and_agent_move game_id={game_id}")
                    agent = games.get(game_id, None)
                    new_game_state = contents.get("new_game_state")
                    print(f"[ws] new_game_state={new_game_state}")

                    if agent is None:
                        print(f"[ws] unknown_game_id={game_id}; active_games={list(games.keys())}")
                        await ws.send(json.dumps({
                            "message_type": "agent_turn_failed",
                            "reason": "unknown_game_id",
                            "game_id": game_id,
                        }))
                        continue

                    print(f"[ws] starting agent turn game_id={game_id}")
                    asyncio.create_task(run_agent_turn(current_ws, agent, game_id, new_game_state))
                    


    except Exception as e:
        print(f"the websocket server hit this error: {e}")
        traceback.print_exc()



async def main():
    async with websockets.serve(handler, "localhost", 3078):
        print("websocket server active!")
        await asyncio.Future()


asyncio.run(main())
