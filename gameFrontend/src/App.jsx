import { useMemo, useState, useEffect, useRef } from "react";
import useAgent from "../gameHooks";
import { z } from 'zod';

const EMPTY_BOARD = Array(9).fill(null);
const HUMAN = "X";
const AGENT = "O";

const WINNING_LINES = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

function getGameResult(board) {
  for (const line of WINNING_LINES) {
    const [a, b, c] = line;

    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return {
        winner: board[a],
        winningLine: line,
        isDraw: false,
        isFinished: true,
      };
    }
  }

  const isDraw = board.every(Boolean);

  return {
    winner: null,
    winningLine: [],
    isDraw,
    isFinished: isDraw,
  };
}

function buildMoveSummary({ board, player, slotIndex, result }) {
  return {
    player,
    slotIndex,
    board,
    winner: result.winner,
    isDraw: result.isDraw,
    isFinished: result.isFinished,
  };
}

export default function App() {
  const [board, setBoard] = useState(EMPTY_BOARD);
  const [turn, setTurn] = useState(HUMAN);
  const [moveLog, setMoveLog] = useState([]);
  const [lastAgentToolCall, setLastAgentToolCall] = useState(null);
  const [ gameId, setGameId ] = useState(() => crypto.randomUUID());
  const [gameStarted, setGameStarted] = useState(false);
  const result = useMemo(() => getGameResult(board), [board]);
  const boardRef = useRef(board);
  const turnRef = useRef(turn);
  const resultRef = useRef(result);
  

   useEffect(() => {
    boardRef.current = board;
    turnRef.current = turn;
    resultRef.current = result;
  }, [board, turn, result]);

  const { addAgentToolsAndSchema, startGame, updateAgentStateAndAgentTurn, addEventChanger } = useAgent(gameId)

  useEffect(() => {

    addEventChanger("human_turn_start", () => setTurn(HUMAN));
    addAgentToolsAndSchema(applyAgentMove, applyAgentMoveSchema, applyAgentMoveSchemaJson, applyAGentMoveSchemaDescription);

  },[])

  

  

  function commitMove(slotIndex, player) {
    const currentBoard = boardRef.current;
    const currentTurn = turnRef.current;
    const currentResult = resultRef.current;

    if (currentResult.isFinished) {
      return { ok: false, reason: "game_finished", board: currentBoard, result: currentResult };
    }

    if (currentTurn !== player) {
      return { ok: false, reason: "wrong_turn", board: currentBoard, result: currentResult };
    }

    if (!Number.isInteger(slotIndex) || slotIndex < 0 || slotIndex > 8) {
      return { ok: false, reason: "invalid_slot", board: currentBoard, result: currentResult };
    }

    if (currentBoard[slotIndex]) {
      return { ok: false, reason: "slot_taken", board: currentBoard, result: currentResult };
    }

    const nextBoard = currentBoard.map((value, index) =>
      index === slotIndex ? player : value
    );
    const nextResult = getGameResult(nextBoard);

    setBoard(nextBoard);
    // should this really be set here? otherwise, agent can still be responding to turn post-tool call, whilst already moved to human turn
    //setTurn(nextResult.isFinished ? null : player === HUMAN ? AGENT : HUMAN);
    setMoveLog((items) => [
      buildMoveSummary({
        board: nextBoard,
        player,
        slotIndex,
        result: nextResult,
      }),
      ...items,
    ]);

    return { ok: true, board: nextBoard, result: nextResult };
  }

  function handleHumanMove(slotIndex) {
    if (!gameStarted) {
      return { ok: false, reason: "game_not_started", board, result };
    }

    const move = commitMove(slotIndex, HUMAN);

    if (move.ok) {
      // Wire this into your custom hook: send the updated board/move to the agent.
      // Example payload for websocket type "human_tool_call":
      // { previous_human_move: move.board, slotIndex, gameResult: move.result }
      console.log("human_move", {
        slotIndex,
        board: move.board,
        result: move.result,
      });
    }

    // need to send update to AI Agent, then trigger new move
    if (move.ok && !move.result.isFinished) {
      console.log("Human turn finished - game not over - triggering agent turn")
      setTurn(AGENT)
      updateAgentStateAndAgentTurn({ board: move.board, lastMove: { player: HUMAN, slotIndex }, result: move.result})
    }

    return move;
  }

  function applyAgentMove({ row, column }) {
    const slotIndex = row * 3 + column;
    const move = commitMove(slotIndex, AGENT);

    setLastAgentToolCall({
      slotIndex,
      ok: move.ok,
      reason: move.reason ?? null,
    });

    // Wire this into your custom hook: return this object as the tool result.
    // Example payload for websocket type "tool_call_response":
    // { tool_call_id: toolCallId, tool_call_result: move }
    return move;
  }



  const applyAgentMoveSchema = z.object({
    row: z.number().int().min(0).max(2),
    column: z.number().int().min(0).max(2)
  })

  const applyAgentMoveSchemaJson = z.toJSONSchema(applyAgentMoveSchema);
  const applyAGentMoveSchemaDescription = "This tool allows you to execute your turn by adding a new piece to the tic-tac-toe board"




  

  function resetGame() {
    setBoard(EMPTY_BOARD);
    setTurn(HUMAN);
    setMoveLog([]);
    setLastAgentToolCall(null);
    const newGameId = crypto.randomUUID()
    setGameId(newGameId)
    setGameStarted(false)
  }

  async function startNewGame() {
    const started = await startGame(gameId);
    if (started) {
      setGameStarted(true);
    }
  }



  const statusText = result.winner
    ? `${result.winner === HUMAN ? "Human" : "Agent"} wins`
    : result.isDraw
      ? "Board locked: draw"
      : gameStarted
        ? `${turn === HUMAN ? "Human" : "Agent"} to move`
        : "Start the game";

  return (
    <main className="appShell">
      <section className="gamePanel" aria-label="Three in a row game">
        <div className="scoreRail" aria-label="Players">
          <div className={`playerBadge ${turn === HUMAN ? "isActive" : ""}`}>
            <span className="mark markHuman">X</span>
            <span>Human</span>
          </div>
          <div className={`playerBadge ${turn === AGENT ? "isActive" : ""}`}>
            <span className="mark markAgent">O</span>
            <span>Agent</span>
          </div>
        </div>

        <div className="boardWrap">
          <div className="statusRow">
            <p>{statusText}</p>
            <div className="actionButtons">
              <button type="button" className="resetButton" onClick={startNewGame} disabled={gameStarted}>
                Start
              </button>
              <button type="button" className="resetButton" onClick={resetGame}>
                Reset
              </button>
            </div>
          </div>

          <div className="board" role="grid" aria-label="Game board">
            {board.map((slot, index) => {
              const isWinningSlot = result.winningLine.includes(index);

              return (
                <button
                  aria-label={`Slot ${index + 1}${slot ? `, ${slot}` : ""}`}
                  className={`slot ${slot ? "isFilled" : ""} ${
                    isWinningSlot ? "isWinner" : ""
                  }`}
                  disabled={!gameStarted || turn !== HUMAN || Boolean(slot) || result.isFinished}
                  key={index}
                  onClick={() => handleHumanMove(index)}
                  role="gridcell"
                  type="button"
                >
                  <span className={slot === HUMAN ? "markHuman" : "markAgent"}>
                    {slot}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="moveLog" aria-label="Move log">
        {moveLog.length === 0 ? (
          <p>No moves yet.</p>
        ) : (
          moveLog.map((move, index) => (
            <p key={`${move.player}-${move.slotIndex}-${index}`}>
              {move.player === HUMAN ? "Human" : "Agent"} placed {move.player} in
              slot {move.slotIndex + 1}
            </p>
          ))
        )}
      </section>
    </main>
  );
}
