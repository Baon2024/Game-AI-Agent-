import { useEffect, useRef, useState } from "react";
import speakMoveReasoning from "./elevenlabsHelper";

export default function useAgent(gameId) {
  //const [agentToolsAndSchema, setAgentToolsAndSchema] = useState({});
  //const [eventChangers, setEventChangers] = useState({});
  const agentToolsAndSchema = useRef({});
  const eventChangers = useRef({});
  const wsRef = useRef(null);
  const webSocketUrl = "ws://localhost:3078";


  function addEventChanger(newEvent, callbackFunc) {
    console.log("[agent-hook] registering event handler", { event: newEvent });
    eventChangers.current[newEvent] = callbackFunc;
  }

  function addAgentToolsAndSchema(newFunc, newFuncSchema, jsonNewFuncSchema, description) {

    console.log("[agent-hook] registering agent tool", {
      name: newFunc.name,
      description,
      jsonSchema: jsonNewFuncSchema,
    });

    agentToolsAndSchema.current[newFunc.name] = {
        fn: newFunc,
        schema: newFuncSchema,
        jsonSchema: jsonNewFuncSchema,
        description,
      }

    }
  

  function executeAgentTool(toolName, toolArgs) {
    console.log("[agent-hook] executing agent tool", {
      toolName,
      toolArgs,
      registeredToolNames: Object.keys(agentToolsAndSchema.current),
    });

    const tool = agentToolsAndSchema.current[toolName];

    if (!tool) {
      console.error("[agent-hook] tool not found", {
        toolName,
        registeredToolNames: Object.keys(agentToolsAndSchema.current),
      });
      return {
        ok: false,
        reason: "tool_with_that_name_does_not_exist",
        toolName,
      };
    }

    const parsedArgs = tool.schema.safeParse(toolArgs ?? {});

    if (!parsedArgs.success) {
      console.error("[agent-hook] tool args failed validation", {
        toolName,
        toolArgs,
        errors: parsedArgs.error.flatten(),
      });
      return {
        ok: false,
        reason: "invalid_arguments",
        errors: parsedArgs.error.flatten(),
      };
    }

    try {
      const result = tool.fn(parsedArgs.data ?? {});
      console.log("[agent-hook] tool execution result", {
        toolName,
        result,
      });
      return result;
    } catch (error) {
      console.error("[agent-hook] tool execution threw", {
        toolName,
        error,
      });
      return {
        ok: false,
        reason: "tool_execution_failed",
        message: error instanceof Error ? error.message : String(error),
      };
    }
  }

  async function triggerNewGame(nextGameId = gameId) {
    const toolsSchema = Object.entries(agentToolsAndSchema.current).map(([name, tool]) => ({
      type: "function",
      function: {
        name,
        description: tool.description,
        parameters: tool.jsonSchema,
      },
    }));

    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn("[agent-hook] triggerNewGame skipped because websocket is not open", {
        nextGameId,
        readyState: wsRef.current?.readyState,
        toolCount: toolsSchema.length,
      });
      return false;
    }

    console.log("[agent-hook] sending new_game", {
      newGameId: nextGameId,
      toolCount: toolsSchema.length,
      toolsSchema,
    });

    wsRef.current.send(JSON.stringify({
      message_type: "new_game",
      tools_schema: toolsSchema,
      new_game_id: nextGameId,
    }));

    return true;
  }

  async function updateAgentStateAndAgentTurn(newGameState) {
    console.log("[agent-hook] sending update_game_state_and_agent_move", {
      gameId,
      newGameState,
      readyState: wsRef.current?.readyState,
    });

    wsRef.current?.send(JSON.stringify({
      message_type: "update_game_state_and_agent_move",
      game_id: gameId,
      new_game_state: newGameState,
    }));
  }

  async function startGame(newGameId) {

    const toolsSchema = Object.entries(agentToolsAndSchema.current).map(([name, tool]) => ({
      type: "function",
      function: {
        name,
        description: tool.description,
        parameters: tool.jsonSchema,
      },
    }));

    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn("[agent-hook] startGame skipped because websocket is not open", {
        newGameId,
        readyState: wsRef.current?.readyState,
        toolCount: toolsSchema.length,
      });
      return false;
    }

    console.log("[agent-hook] sending new_game from startGame", {
      newGameId,
      toolCount: toolsSchema.length,
      toolsSchema,
    });

    wsRef.current.send(JSON.stringify({
      message_type: "new_game",
      tools_schema: toolsSchema,
      new_game_id: newGameId,
    }));

    return true;

  }

  useEffect(() => {
    console.log("[agent-hook] opening websocket", { webSocketUrl });
    const wsClient = new WebSocket(webSocketUrl);
    wsRef.current = wsClient;

    wsClient.onopen = () => {
      console.log("[agent-hook] websocket open", {
        readyState: wsClient.readyState,
      });
    };

    wsClient.onerror = (event) => {
      console.error("[agent-hook] websocket error", event);
    };

    wsClient.onclose = (event) => {
      console.warn("[agent-hook] websocket closed", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
      });
    };

    

    wsClient.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      const messageType = data.message_type;
      console.log("[agent-hook] websocket message received", data);

      if (messageType === "agent_tool_call") {
        const toolName = data.tool_call_name;
        const toolCallId = data.tool_call_id;
        const toolArgs = data.tool_call_arguments ?? {};

        // code to speak the message
        const toolReasoning = data.move_reasoning ?? null
        void speakMoveReasoning(toolReasoning)


        const result = executeAgentTool(toolName, toolArgs);
        console.log("[agent-hook] sending tool_call_response", {
          toolName,
          toolCallId,
          result,
        });

        await wsRef.current?.send(JSON.stringify({
          message_type: "tool_call_response",
          tool_call_id: toolCallId,
          tool_call_result: result,
        }));
      } else if (messageType === "human_turn_start") {
        console.log("[agent-hook] human_turn_start received", {
          registeredEvents: Object.keys(eventChangers.current),
        });
        const changeTurnFunc = eventChangers.current[messageType];
        changeTurnFunc();

      } else {
        console.warn("[agent-hook] unhandled websocket message", data);
      }
    };

    return () => wsClient.close();
  }, []);

  return {
    updateAgentStateAndAgentTurn,
    addAgentToolsAndSchema,
    addEventChanger,
    triggerNewGame,
    startGame
  };
}
