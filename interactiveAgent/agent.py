from __future__ import annotations
import json
import re
from dataclasses import dataclass

from dotenv import load_dotenv



load_dotenv()

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict





class ToDoItem(BaseModel):
    # required shape for each item
    step: str
    status: Literal["pending", "in_progress", "done"] = "pending"
    details: Optional[str] = None

    # let the LLM add extra per-item fields (e.g., "owner", "priority")
    model_config = ConfigDict(extra='forbid')

class ToDoList(BaseModel):
    # list can have any number of items (including zero)
    todo_list: List[ToDoItem] = Field(default_factory=list)

    # keep progress predictable (e.g., "0% completed")
    model_config = ConfigDict(extra="forbid")


# --- Actions ---
def calculate(what: str):
    return eval(what, {"__builtins__": {}})  # basic safety

def average_dog_weight(name: str):
    n = name.strip().lower()
    if n in {"scottish terrier", "scottie"}:
        return "Scottish Terriers average 20 lbs"
    elif n in {"border collie", "collie"}:
        return "A Border Collie's average weight is 37 lbs"
    elif n in {"toy poodle", "toy-poodle"}:
        return "A Toy Poodle's average weight is 7 lbs"
    else:
        return "An average dog weighs 50 lbs"

from firecrawl import Firecrawl

firecrawl = Firecrawl(api_key="fc-3bcef77f2ef94ebfae02c9301e20ac30")



def firecrawl_search(state, search: str, number_of_results: int = 3):
    """This tool allows you to search the internet, using Firecrawl.
    
    Input:
      search: str - the query you want to search
      number_of_results: int (Optional) - the number of results you want. The default is 3, if you don't choose a number. 
    
    """

    results = firecrawl.search(
        search,
        limit=number_of_results
    )
    print(f"results from firecrawl are: {results}")
    return { "results": results, "number_of_results": number_of_results}


known_actions = { ## this is use for both basic agent
    "calculate": calculate,
    "average_dog_weight": average_dog_weight,
    "no_action": lambda s: s,  # echo for completeness
    
}

# --- System prompt requesting brief rationale, not chain-of-thought ---
system_prompt = """
You are a tool-using assistant that works in a loop of (Rationale → Action → Observation) 
until you can provide a final answer.

Return output STRICTLY as compact JSON with this schema:

{
  "rationale": "1-2 sentence high-level reason for your next step. Do NOT reveal steps or chain-of-thought.",
  "action": "one of: calculate | average_dog_weight | no_action",
  "action_input": "string input for the action (or empty for no_action)",
  "final_answer": null | "string answer if you are ready to answer the user now"
}



Rules:
- Keep "rationale" brief and non-enumerated (no step-by-step).
- If you know the answer now, set "final_answer" and use "no_action" with empty input.
- If you need to use a tool, set "action" to that tool and provide "action_input". Leave "final_answer" as null.
- Never include additional keys. The entire message MUST be valid JSON.
""".strip()


@dataclass
class Agent:
    system: str = ""

    def __post_init__(self):
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": self.system})
    
    def todo_generation(self, question: str):
        message = f"""You need to generate a todo list to plan your steps answering the following question, and track your progress.
        The query is: *{question}*
        
        The format should be json, and in the following format: {ToDoList.model_json_schema}

        """
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.5,
            messages=[{"role": "user", "content": message}],
            response_format={"type": "json_object"}
        )
        text = completion.choices[0].message.content
        try:
            text = json.loads(text)
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e


    def __call__(self, message: str):
        self.messages.append({"role": "user", "content": message})
        result_obj = self.execute()
        # Store assistant JSON string to keep conversation state consistent
        self.messages.append({"role": "assistant", "content": json.dumps(result_obj)})
        return result_obj

    def execute(self) -> dict:
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},  # force JSON you can parse
            messages=self.messages,
        )
        text = completion.choices[0].message.content
        print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        try:
            obj = json.loads(text)
            obj["tokens_used"] = completion.usage.total_tokens
        except Exception as e:
            # Fallback if model slightly deviates
            raise ValueError(f"Model did not return valid JSON: {text}") from e
        # Minimal validation
        for k in ["rationale", "action", "action_input", "final_answer"]:
            if k not in obj:
                obj[k] = None
        return obj

##original agent loo

# --- Driver loop that surfaces rationale and observation ---
def query(question: str, num_cycles: int = 5):
    bot = Agent(system_prompt)
    next_input = question
    tokens_used = 0

    
    for i in range(num_cycles):


        step = bot(next_input)#in todo version, you need to give todo list in every call, to agent can see it. but dont save it in self
        #when todo list is comleted, it should then choose to return final answer naturally
        tokens_used += step["tokens_used"]
        # Show the concise rationale each turn
        print(f"Reasoning: {step['rationale']}")
        if step.get("final_answer"):
            print(f"total tokens_used: {tokens_used}")
            return "Answer: " + step["final_answer"], tokens_used

        action = step.get("action")#could later add a "edit todo list" functuon, which would ass existing list, ask for new one back, and udate todo list
        action_input = (step.get("action_input") or "").strip()

        if action not in known_actions:
            raise Exception(f"Unknown action: {action}")

        # Run tool
        observation = known_actions[action](action_input) #need to add custom_state to whatever arameters returned by LLM
        print(f"Action: {action}: {action_input}\nObservation: {observation}")

        # Feed observation back, with a newline to keep turns clear
        next_input = f"Observation: {observation}\n"

        #udate to do list by assing it to new method of agent, that doesnt add todo list to self.messages but does combine them for agent to assess
        #whether comoleted, without saving this snashot
        #would go to new agent method, that adds nextinut on to of existing messages, and todo list, and asks for udated todo list back
        #then arse returned stuff inside that method, and take resonse here and udate todo list to equal that

    
    return "Answer: (no answer within allotted cycles)" + tokens_used



# Full multi-turn question
# result, tokens_used = query("I have 2 dogs, a Border Collie and a Scottish Terrier. What is their combined weight?")
# print(result)
# print(f"total tokens_used: {tokens_used}")


from datetime import date

DEFAULT_STATE = {
    "meta": {
        "run_id": None,          # filled at init
        "cycle": 0,
        "status": "idle",
    },
    "question": None,
    "current_date": date.today().isoformat(),
    "user_language": "English",
    "memory": {},                # key/value facts
    "todo": [],                  # list of steps
    "working_notes": {},         # scratch info by subagent/tool
    "history": [],               # [{"role":"user/agent","content":"..."}]
    "artifacts": [],             # file/urls or results
}

# move initial state to have most of these, so its more comlete

class CustomState:

    def __init__(self):
        self.state = DEFAULT_STATE
    
    def get_state(self):
        return self.state
    
    def set_state(self, new_state):
        self.state = new_state


#Agent + State

def calculate_state_version(state: CustomState, what: str):
    return eval(what, {"__builtins__": {}})  # basic safety

def average_dog_weight_state_version(state: CustomState, name: str):
    
    local_state = state.get_state()

    n = name.strip().lower()
    if n in {"scottish terrier", "scottie"}:
        local_state['average_dog_weight for scottish terrier'] = "Scottish Terriers average 20 lbs"
        state.set_state(local_state)
        return "Scottish Terriers average 20 lbs"
    elif n in {"border collie", "collie"}:
        local_state['average_dog_weight for border collie'] = "A Border Collie's average weight is 37 lbs"
        state.set_state(local_state)
        return "A Border Collie's average weight is 37 lbs"
    elif n in {"toy poodle", "toy-poodle"}:
        local_state['average_dog_weight for toy poodle'] = "A Toy Poodle's average weight is 7 lbs"
        state.set_state(local_state)
        return "A Toy Poodle's average weight is 7 lbs"
    else:
        local_state['average_dog_weight for dog not in list '] = "An average dog weighs 50 lbs"
        state.set_state(local_state)
        return "An average dog weighs 50 lbs"


known_actions_state_version = { ## this is used for basic agent + state
    "calculate": calculate,
    #"average_dog_weight": average_dog_weight,
    "no_action": lambda s: s,  # echo for completeness
    "calculate_state_version": calculate_state_version,
    "average_dog_weight_state_version": average_dog_weight_state_version,
    "firecrawl_search": firecrawl_search
}


system_prompt_state_version = """
You are a tool-using assistant that works in a loop of (Rationale → Action → Observation) 
until you can provide a final answer.

Return output STRICTLY as compact JSON with this schema:

{
  "rationale": "1-2 sentence high-level reason for your next step. Do NOT reveal steps or chain-of-thought.",
  "action": "one of: calculate_state_version | average_dog_weight_state_version | no_action",
  "action_input": "string input for the action (or empty for no_action)",
  "final_answer": null | "string answer if you are ready to answer the user now"
}

function average_dog_weight_state_version:
  action_input: string of one dog breed name. for exam

Rules:
- Keep "rationale" brief and non-enumerated (no step-by-step).
- If you know the answer now, set "final_answer" and use "no_action" with empty input.
- If you need to use a tool, set "action" to that tool and provide "action_input". Leave "final_answer" as null.
- Never include additional keys. The entire message MUST be valid JSON.
""".strip()


state = CustomState() # create seerate one for memory, subagents and todo list features


def queryStateVersion(question: str, state: CustomState, num_cycles: int = 5):
    bot = Agent(system_prompt_state_version)
    next_input = question
    tokens_used = 0
    local_state = state.get_state()
    local_state['question'] = question
    state.set_state(local_state)

    
    for i in range(num_cycles):


        step = bot(next_input)#in todo version, you need to give todo list in every call, to agent can see it. but dont save it in self
        #when todo list is comleted, it should then choose to return final answer naturally
        tokens_used += step["tokens_used"]
        # Show the concise rationale each turn
        print(f"Reasoning: {step['rationale']}")
        if step.get("final_answer"):
            print(f"total tokens_used: {tokens_used}")
            return "Answer: " + step["final_answer"], tokens_used

        action = step.get("action")#could later add a "edit todo list" functuon, which would ass existing list, ask for new one back, and udate todo list
        action_input = (step.get("action_input") or "").strip()

        if action not in known_actions_state_version:
            raise Exception(f"Unknown action: {action}")

        # Run tool
        observation = known_actions_state_version[action](state, action_input) #need to add custom_state to whatever arameters returned by LLM
        print(f"Action: {action}: {action_input}\nObservation: {observation}")

        # Feed observation back, with a newline to keep turns clear
        next_input = f"Observation: {observation}\n"

        #udate to do list by assing it to new method of agent, that doesnt add todo list to self.messages but does combine them for agent to assess
        #whether comoleted, without saving this snashot
        #would go to new agent method, that adds nextinut on to of existing messages, and todo list, and asks for udated todo list back
        #then arse returned stuff inside that method, and take resonse here and udate todo list to equal that

    
    return "Answer: (no answer within allotted cycles)" + tokens_used

#result, tokens_used = queryStateVersion("I have 2 dogs, a Border Collie and a Scottish Terrier. What is their combined weight?", state)
#print(result)
#print(f"total tokens_used: {tokens_used}")
#print(f"state after agent run is {state.get_state()}") #python app2.py



# --- state + todo list

system_prompt_state_version_todo = """
You are a tool-using assistant that works in a loop of (Rationale → Action → Observation) 
until you can provide a final answer.

Return output STRICTLY as compact JSON with this schema:

{
  "rationale": "1-2 sentence high-level reason for your next step. Do NOT reveal steps or chain-of-thought.",
  "action": "one of: calculate_state_version | average_dog_weight_state_version | firecrawl_search | no_action ",
  "action_input": "string input for the action (or empty for no_action)",
  "final_answer": null | "string answer if you are ready to answer the user now"
}

function average_dog_weight_state_version:
  action_input: string of one dog breed name. for exam

function firecrawl_search:
  search: str of term or phrase to search the web for
  number_of_results: the number of results you want 

Rules:
- Keep "rationale" brief and non-enumerated (no step-by-step).
- If you know the answer now, set "final_answer" and use "no_action" with empty input.
- If you need to use a tool, set "action" to that tool and provide "action_input". Leave "final_answer" as null.
- Never include additional keys. The entire message MUST be valid JSON.
""".strip()

@dataclass
class AgentToDo:
    system: str = ""

    def __post_init__(self):
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": self.system})
    
    def todo_generation(self, question: str):
        message = f"""You need to generate a todo list to plan your steps answering the following question, and track your progress.
        The query is: *{question}*
        
        The format should be json, and in the following format: {ToDoList.model_json_schema}

        """
        completion = client.chat.completions.parse(
            model="gpt-4o",
            temperature=0.5,
            messages=[{"role": "user", "content": message}],
            response_format=ToDoList,
        )
        text = completion.choices[0].message.content
        try:
            text = json.loads(text)
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e
    
    def todo_generation_markdown(self, question: str):
        message = f"""You need to generate a todo list to plan your steps answering the following question, and track your progress.
        The query is: *{question}*
        
        The format should be as text

        """
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.5,
            messages=[{"role": "user", "content": message}],
        )
        text = completion.choices[0].message.content
        try:
            #text = json.loads(text)
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e


    def __call__(self, message: str,):
        self.messages.append({"role": "user", "content": message})
        result_obj = self.execute()
        # Store assistant JSON string to keep conversation state consistent
        self.messages.append({"role": "assistant", "content": json.dumps(result_obj)})
        return result_obj
    
    def get_next_step(self, message, todo_list):
        self.messages.append({"role": "user", "content": message})

        plan_message = f"""This is your current plan: {todo_list} 
        """
        #if this is called after first initial user task, when "next_step" is really a tool call result
        #it needs to dynamically decide whether to add it's appearance as a param here, as "user" role, or "tool" role
        if "tool" in message:
            print("🛠️ the next_step passed to get_next_step is the result of a tool call! 🛠️")

        self.messages.append({"role": "user", "content": plan_message })
        
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},  # force JSON you can parse
            messages=self.messages,
        )
        text = completion.choices[0].message.content
        print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        
        
        try:
            obj = json.loads(text)
            obj["tokens_used"] = completion.usage.total_tokens
        except Exception as e:
            # Fallback if model slightly deviates
            raise ValueError(f"Model did not return valid JSON: {text}") from e
        # Minimal validation
        for k in ["rationale", "action", "action_input", "final_answer"]:
            if k not in obj:
                obj[k] = None
        self.messages.append({"role": "assistant", "content": json.dumps(obj)})
        return obj
    
    def review_todo_after_action(self, todo_list, action_result):
        messages = self.messages
        messages.append({"role": "user", "content": action_result})

        prompt_messages = f"""Youve just taken a new action, so your action list is now: {messages} 
        
        Your existing plan before the latest step is:  {todo_list}.

        return your updated version of the plan, which can have changes or be the same. Your updated json version must adhere to this format: {ToDoList.model_json_schema()}
        
        """
        print(f"prompt_messages for new todo list: {prompt_messages}")

        completion = client.chat.completions.parse(
            model="gpt-4o",
            temperature=0,
            response_format=ToDoList,  # force JSON you can parse
            messages=[{"role": "user", "content": prompt_messages}],
        )
        text = completion.choices[0].message.content
        try:
            text = json.loads(text)
            print(f"updated version of the plan: {text}")
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e
    
    def review_todo_after_action_markdown(self, todo_list, action_result):
        messages = self.messages
        messages.append({"role": "user", "content": action_result})

        prompt_messages = f"""Youve just taken a new action, so your action list is now: {messages} 
        
        Your existing plan before the latest step is:  {todo_list}.

        return your updated text version of the plan, which can have changes or be the same.
        
        """
        print(f"prompt_messages for new todo list: {prompt_messages}")

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[{"role": "user", "content": prompt_messages}],
        )
        text = completion.choices[0].message.content
        try:
            #text = json.loads(text)
            print(f"updated version of the plan: {text}")
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e


    def execute(self) -> dict:
        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},  # force JSON you can parse
            messages=self.messages,
        )
        text = completion.choices[0].message.content
        print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        try:
            obj = json.loads(text)
            obj["tokens_used"] = completion.usage.total_tokens
        except Exception as e:
            # Fallback if model slightly deviates
            raise ValueError(f"Model did not return valid JSON: {text}") from e
        # Minimal validation
        for k in ["rationale", "action", "action_input", "final_answer"]:
            if k not in obj:
                obj[k] = None
        return obj



def queryToDo(question: str, state: CustomState, num_cycles: int = 5):
    bot = AgentToDo(system_prompt_state_version_todo)
    next_input = question
    tokens_used = 0
    local_state = state.get_state()
    local_state['question'] = question
    # conditional call to bot, Agent, to ask whether task requires todo list, with different conitional aths for each one
    todo_list = bot.todo_generation(local_state['question'])
    print(f"value of todo list is: {todo_list}")
    local_state['todo_list'] = todo_list
    

    

   

    for i in range(num_cycles):


        step = bot.get_next_step(next_input, local_state['todo_list'])#in todo version, you need to give todo list in every call, to agent can see it. but dont save it in self
        #when todo list is comleted, it should then choose to return final answer naturally
        print(f"result from step is: {step}")
        tokens_used += step["tokens_used"]
        # Show the concise rationale each turn
        print(f"Reasoning: {step['rationale']}")
        if step.get("final_answer"):
            print(f"total tokens_used: {tokens_used}")
            state.set_state(local_state)#only need to udate global state at the end
            print(f"self.messages at the end is: {bot.messages}")
            return "Answer: " + step["final_answer"], tokens_used

        action = step.get("action")#could later add a "edit todo list" functuon, which would ass existing list, ask for new one back, and udate todo list
        action_input = (step.get("action_input") or "").strip()

        if action not in known_actions_state_version:
            raise Exception(f"Unknown action: {action}")

        # Run tool
        observation = known_actions_state_version[action](state, action_input) #need to add custom_state to whatever arameters returned by LLM
        print(f"Action: {action}: {action_input}\nObservation: {observation}")

        # Feed observation back, with a newline to keep turns clear
        next_input = f"Observation: {observation}\n"
        local_state['todo_list'] = bot.review_todo_after_action(local_state['todo_list'], next_input)

        #need to return udated todo list, but dont add next inut to messages, as that will be done above

        #udate to do list by assing it to new method of agent, that doesnt add todo list to self.messages but does combine them for agent to assess
        #whether comoleted, without saving this snashot
        #would go to new agent method, that adds nextinut on to of existing messages, and todo list, and asks for udated todo list back
        #then arse returned stuff inside that method, and take resonse here and udate todo list to equal that

    
    return "Answer: (no answer within allotted cycles)" + tokens_used



# Full multi-turn question
#result, tokens_used = queryToDo("I have 2 dogs, a Border Collie and a Scottish Terrier. What is their combined weight?", state)
#print(result)
#print(f"total tokens_used: {tokens_used}")


#version with filesystem todo list, rather than object/class

from pathlib import Path

def queryToDoFileSemi1(question: str, state: CustomState, system_prompt_state_version_todo, num_cycles: int = 15):
    bot = AgentToDo(system_prompt_state_version_todo)
    next_input = question
    tokens_used = 0
    local_state = state.get_state()
    local_state['question'] = question
    # conditional call to bot, Agent, to ask whether task requires todo list, with different conitional aths for each one
    todo_list = bot.todo_generation(local_state['question'])
    print(f"value of todo_list is: {todo_list}" )
    #now write todo_list to filesystem
    todo_list_str = str(todo_list)
    markdown_todo_list = "\n".join(f"Step - ** {k}: {v}" for k, v in todo_list["todo_list"][0].items())
    print(f"value of markdown_todo_list is: {markdown_todo_list}")
    current_dir = Path(__file__).parent
    md_path = current_dir / "todo_list.md"

    md_path.write_text(todo_list_str, encoding="utf-8")
    print(f"✅ To-do list saved to: {md_path}")

    print(f"value of todo list is: {todo_list}")
    local_state['todo_list'] = todo_list
    

    

   

    for i in range(num_cycles):


        step = bot.get_next_step(next_input, local_state['todo_list'])#in todo version, you need to give todo list in every call, to agent can see it. but dont save it in self
        #when todo list is comleted, it should then choose to return final answer naturally
        print(f"result from step is: {step}")
        tokens_used += step["tokens_used"]
        # Show the concise rationale each turn
        print(f"Reasoning: {step['rationale']}")
        if step.get("final_answer"):
            print(f"total tokens_used: {tokens_used}")
            state.set_state(local_state)#only need to udate global state at the end
            print(f"self.messages at the end is: {bot.messages}")
            md_path.write_text(str(local_state["todo_list"]), encoding="utf-8")

            return "Answer: " + step["final_answer"], tokens_used

        action = step.get("action")#could later add a "edit todo list" functuon, which would ass existing list, ask for new one back, and udate todo list
        action_input = (step.get("action_input") or "").strip()

        if action not in known_actions_state_version:
            raise Exception(f"Unknown action: {action}")

        # Run tool
        observation = known_actions_state_version[action](state, action_input) #need to add custom_state to whatever arameters returned by LLM
        print(f"Action: {action}: {action_input}\nObservation: {observation}")

        # Feed observation back, with a newline to keep turns clear
        next_input = f"Observation from tool call: {observation}\n"
        local_state['todo_list'] = bot.review_todo_after_action(local_state['todo_list'], next_input)

        #need to return udated todo list, but dont add next inut to messages, as that will be done above

        #udate to do list by assing it to new method of agent, that doesnt add todo list to self.messages but does combine them for agent to assess
        #whether comoleted, without saving this snashot
        #would go to new agent method, that adds nextinut on to of existing messages, and todo list, and asks for udated todo list back
        #then arse returned stuff inside that method, and take resonse here and udate todo list to equal that

    
    return "Answer: (no answer within allotted cycles)", tokens_used



# Full multi-turn question
#result, tokens_used = queryToDoFileSemi1("what is tottenham hotspur? you should search the web for answers ", state, system_prompt_state_version_todo)
#print(result)
#print(f"total tokens_used: {tokens_used}")






##should be pretty easy to add skills, just needs to be a function that allows opening of a file, re-used for all skills
##maybe need to allow re-writing of todo_list after accessing new info from skill, but not neccesarily
##and adding agent should be pretty easy, too



#version whether file system interaction is via functions, not hard-coded

def write_todo(todo_file_name: str, todo_list_contents: str):


    current_dir = Path(__file__).parent
    md_path = current_dir / f"{todo_file_name}.md"
    if type(todo_list_contents) == str:
        md_path.write_text(todo_list_contents, encoding="utf-8")
        return f"{todo_file_name} successfuly created!"
    else:
        md_path.write_text(str(todo_list_contents), encoding="utf-8")





sub_agent_literature_prompt = """"""

known_sub_agents = {
    "sub_agent_researcher": system_prompt_state_version_todo
}

from pathlib import Path

def how_to_web_search(state):
    "function to get info from markdown file on how to search the web"

    parent_directory = Path(__file__).parent
    how_to_web_search_location = parent_directory / "how_to_web_search.md"

    file_contents = how_to_web_search_location.read_text()

    return f"how_to_web_search.md file succesfuly read. These are the instructions: {file_contents}"



import subprocess
from typing import Dict
import shlex

import os
import shlex
import subprocess
import sys
import traceback
from typing import Dict, Any, Optional



def ask_user_followup(state, question):
    """
    This function allows you to ask the user for further detail about the task they've given you.

    Inputs:
      question: ask the user what you want to clarify (your query)
    
    Outputs:
      user_response: the user's response
    """

    #print(question)
    user_response = input(question) #ask user soemthing

    return { "user_response": user_response}

def run_python(state, code: str, cwd: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
    """
    Run a command (Python-related or general) with NO sandbox.
    - code: e.g. "python C:\\path\\to\\script.py" or "git status"
    - cwd: optional working directory; if None uses current process cwd.
    Always returns a dict; never raises.


    *DO NOT RUN "python main.py" OR "python logic.py" FROM THE "my_package" FOLDER

    *When you want to run python code, first write it to a file, then use this function to run that file*
    """
    print("🐍 calling run_python ..")

    try:
        args = shlex.split(code, posix=False)  # Windows-friendly splitting

        if not args:
            return {"ok": False, "stdout": "", "stderr": "Empty command.", "exit_code": 2, "args": []}
        
        args = [a.strip().strip('"') for a in args]

        # Use the current interpreter to avoid PATH issues
        if args[0].lower() == "python":
            args[0] = sys.executable

        # If command is a .py file path, run it with python
        if args[0].lower().endswith(".py"):
            args = [sys.executable] + args

        # Working directory: allow caller override, otherwise inherit
        run_cwd = cwd or os.getcwd()

        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=run_cwd,
            shell=False,   # Option A: no shell features
        )

        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "args": args,
            "cwd": run_cwd,
        }

    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "stdout": e.stdout or "",
            "stderr": (e.stderr or "") + "\nExecution timed out.",
            "exit_code": -1,
            "args": code,
            "cwd": cwd or os.getcwd(),
        }

    except FileNotFoundError as e:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"File/command not found: {e}. Command was: {code}",
            "exit_code": 127,
            "args": code,
            "cwd": cwd or os.getcwd(),
        }

    except Exception as e:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"{type(e).__name__}: {e}",
            "exit_code": 1,
            "args": code,
            "cwd": cwd or os.getcwd(),
            "traceback": traceback.format_exc(),
        }

def write_todo_list(state, todo_list: str) -> str:
    "this function writes a todo list"
    print(f"agent has passed this as todo_list for write_todo_list: {todo_list}")
    print("📝Agent has chosen to create a todo list📝")

    agent_name = state["name"]
    
    parent_directory = Path(__file__).parent
    file_path = f"{agent_name}_todo_list.md"
    full_file_path = parent_directory / file_path
    full_file_path.write_text(todo_list)

    return f"📝todo list successfuly written and saved! The file name to later read or edit it is: {file_path}"
    #return the same fixed path for todo list, at least for main agent (sub-agents would need their own dynamic path)
    
def write_file(state, filename: str, file_type: str, file_content) -> str:
    """this function allow you to write a file. You can also use this to write code to a file, as well as text.
    
    Inputs:
      filename: (str) the name of the file you want to create
      file_type: (str) the type of tile: for example, ".pdf", ".md", ".py"
      file_content: (str) the content of the file you want to insert
    """
    print(f"agent has passed this as file_content for write_file: {file_content}")
    print("📝Agent has chosen to create a todo list📝")

    agent_name = state["name"]
    
    parent_directory = Path(__file__).resolve().parent
    file_path = f"{filename}{file_type}"
    full_file_path = parent_directory / file_path
    full_file_path.write_text(file_content)

    return f"📝file name successfuly written and saved! The file name to later read or edit it is: {file_path}"
    #return the same fixed path for todo list, at least for main agent (sub-agents would need their own dynamic path)

def read_folder_files(state) -> dict:
    """This function will tell you what files exist that you can access"""

    parent_directory = Path(__file__).resolve().parent

    files: List[str] = [
        p.name
        for p in parent_directory.iterdir()
        if p.is_file()
    ]

    return {
        "folder": str(parent_directory),
        "files": sorted(files),
        "count": len(files),
    }

from urllib.parse import urlparse

def read_file(state, file_name: str) -> str: #needs to take file path as param
    """This function allows you to read a specific file
    
    Input:
      file_name: (str) the name of the file, with file type ending. for example, "text.md", or "my_code.py"
    """
    print(f"agent has passed this as todo_list_file_path in read_todo_list: {file_name}")
    
    # 1) Reject URLs early
    parsed = urlparse(file_name)
    if parsed.scheme in ("http", "https"):
        return (
            f"❌ read_file only reads LOCAL files. You passed a URL: {file_name}\n"
            f"Use a web tool (e.g. fetch_url/firecrawl_scrape) to read web pages."
        )
    parent_directory = Path(__file__).resolve().parent
    full_file_path = parent_directory / file_name
    try:
        file_contents = full_file_path.read_text()
    except FileNotFoundError as e:
        print(f"❌file_name {file_name} not found in filesystem!❌")
        file_contents = None
        return f"❌file_name {file_name} not found in filesystem!❌ file contents are: {file_contents}"

    return f"📖 file {file_name} succesfully read! The file contents are: {file_contents}"

def read_todo_list(state, todo_list_file_name: str) -> str: #needs to take file path as param
    print(f"agent has passed this as todo_list_file_path in read_todo_list: {todo_list_file_name}")

    #agent_name = state["name"]

    parent_directory = Path(__file__).parent
    full_file_path = parent_directory / todo_list_file_name
    todo_list_contents = full_file_path.read_text()

    return f"📖 todo list succesfully read! Your current todo list is this: {todo_list_contents}"

def edit_todo_list(state, new_todo_list: str, todo_list_file_name: str) -> str: #needs to take new todo_list file as content
    print(f"agent has passed this as new_todo_list for edit_todo_list: {new_todo_list}")
    print(f"agent has passed this as todo_list_file_name for edit_todo_list: {todo_list_file_name}")
    
    parent_directory = Path(__file__).parent
    full_file_path = parent_directory / todo_list_file_name
    print(f"full_file_path written to is: {full_file_path}")
    full_file_path.write_text(new_todo_list)

    return f"📝Edited todo list successfully written and saved! The file name to later read or edit again is: {full_file_path}"

def music_report_assessor(state, music_report: str) -> str:
    "this function allows you to send a music report to an assessor, who assesses whether the music report meets the criteria for task completion"
    print("🕵️‍♂️music_report_assessor function called🕵️‍♂️")
    #count number of words
    word_count = len(music_report.split())


    if word_count < 1000:
        return f"❌the music report you submitted is too short: your report is {word_count} words long, but needs to be at least 1000 words❌"
    elif word_count > 1500:
        return f"❌the music report you submitted is too long: your report is {word_count} words long, but needs to be less than 1501 words❌" 
    else:
        return "✅the music report you submitted is within the length specified: you music report is valid and can now be returned✅"

known_actions_state_version = { ## this is used for basic agent + state
    "calculate": calculate,
    #"average_dog_weight": average_dog_weight,
    "no_action": lambda s: s,  # echo for completeness
    "calculate_state_version": calculate_state_version,
    "average_dog_weight_state_version": average_dog_weight_state_version,
    "firecrawl_search": firecrawl_search,
    "how_to_web_search": how_to_web_search, #add todo_list functions here
    "write_todo_list": write_todo_list,
    "read_todo_list": read_todo_list,
    "edit_todo_list": edit_todo_list,
    "run_python": run_python,
    "music_report_assessor": music_report_assessor,
    "write_file": write_file,
    "read_file": read_file,
    "read_folder_files": read_folder_files,
    "ask_user_followup": ask_user_followup
}


#here add my function to programatically create the optional tools list, to pass to agent through instantiation 
import inspect




#sub_agent wrapper just needs to return a object of keys and items

def create_sub_agent(name, description, tools: list):
    
    sub_agent_object = {
        "name": name,
        "description": description,
        "tools": tools #i think you can just add all functions as the list, don't need to add under thei names
    }

    #for tool in tools:
        #tool_name = tool.__name__
        #sub_agent_object["tools"][tool_name] = tool
    
    
    print(f"value of create_sub_agent before returning is: {sub_agent_object}")
    return sub_agent_object


#this returns both tools formatted for symste_prompt, and the known_tools_for_agent in order to call tool once chosen
def get_tools_programatically(array_of_tools: list):
    "this function gets the tools, their params and descriptions programatically"
    
    known_tools_for_agents = {}
    tools = []

    for tool in array_of_tools:
        tool_description = tool.__doc__
        sig = inspect.signature(tool)
        param_names= sig.parameters.keys()

        required_params = [{ name: p.annotation for name, p in sig.parameters.items() if name != 'state' and p.default is inspect._empty }]
        optional_params = [{ name: p.annotation for name, p in sig.parameters.items() if name != 'state' and p.default is not inspect._empty }]

        tool_wrapper = {
            "tool_name": tool.__name__,
            "tool_description": tool_description,
            "parameters": {
                "required_parameters": required_params,
                "optional_parameters": optional_params
            }
        }

        tool_name = tool.__name__
        

        tools.append(tool_wrapper)
        known_tools_for_agents[tool_name] = tool
    return known_tools_for_agents, tools
    

#research_sub_agent = create_sub_agent(name="research_sub_agent", description="sub_agent for doing research", tools=[])
#then can pass a list of these sub_agents to main_agent

#i could try and allow sub_agents to have their own sub_agents, by passing the original sub_agents as sub_agents but filtering to exclude the sub_agent being called
#but even if they works, could create many child loops


## with tools fetch dynamically, rather than added to system prompt - except core ones



system_prompt_programatic_sub_agent = """
You are a tool-using assistant that works in a loop of (Rationale → Action → Observation) 
until you can provide a final answer.

You can choose one, or multiple, or no functions or agents to call. if a function's params are None, then strictly return None
If you choose to return final answer, then "actions" should be empty.

*NEVER PASS A *state* VALUE* - exclude it from the params you return (the state will be added automatically, you don't need to give it)

You can choose whether to create a "todo list" for more complex tasks. Your tools to write and save a todo list, read it later,
or edit it can be found under the *todo list functions* section. Any todo list you create should follow this pattern: use numbered point *(1), (2),* (for example)
and each step should be marked as one of "pending" or "in-progress" or "done". Make sure to update the progress of all steps before returning your final answer.


If you aren't certain how to achieve a task, you can get specific instructions by calling one of the "skill" functions

Return output STRICTLY as compact JSON with this schema:



{
  "rationale": "1-2 sentence high-level reason for your next step. Do NOT reveal steps or chain-of-thought.",
  "actions": [
    {
      "name": "//function_name//", //name of the function
      "type": "function",          // "function" | "agent"
      "params": {
        "name": "//param_name", //params of the function
      }
    },
  ],
  "final_answer": null | "string answer if you are ready to answer the user now"
}



    
*filesystem function*

  function read_file:
    params:
      file_name: the name of the file you want to read. for example, "internet_search_result.md"
    description: "use this tool to read named files in the filesystem that you know exist, already know the name of"


*todo list functions*

  function write_todo_list:
    params:
        todo_list: string of your todo_list for how you will answer the question you've been asked
    description: "this function writes (stores) your todo list to a markdown (.md) file"
  
  function read_todo_list:
    params:
        todo_list_file_name: the file name of your todo list
    description: "this function reads your todo list and returns it to you, if you previously created one

  function edit_todo_list:
    params:
      new_todo_list: string of your updated todo list that you want to save
      todo_list_file_name: the file name of your todo list
    description: "this function updates the todo list you've already created, if you previously created one  

*skill functions*

  function how_to_web_search:
    params: 
        None
    description: "this function will retrieve instructions on how you can search the web to find answers to questions"


Rules:
- Keep "rationale" brief and non-enumerated (no step-by-step).
- If you know the answer now, set "final_answer" and use "no_action" with empty input.
- If you need to use a tool, set "action" to that tool and provide "action_input". Leave "final_answer" as null.
- Never include additional keys. The entire message MUST be valid JSON.
""".strip()

import json

def tools_to_prompt(tools):
    return "\n".join(
        json.dumps(t, indent=2, ensure_ascii=False, default=str)
        if isinstance(t, dict) else str(t)
        for t in tools
    )









from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator, FilePath
from copy import deepcopy





class ActionType(str, Enum):
    function = "function"
    agent = "agent"





class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr
    type: ActionType
    params: Dict[str, Any]  # or: Dict[str, Any]

class FileDict(BaseModel):
    file_name: str = Field(
        ...,
        description="the name of the file you want to return to the user as part of the final answer"
    )
    #file_path: FilePath = Field( # FilePath ensures whatever returns is a file path and exists
        #...,
        #description="the file path of the file you want to return to the user as part of the final answer"
    #)  

class FinalAnswer(BaseModel):
    answer: str = Field(
        ...,
        description="the final answer for the task."
    )
    files: Optional[List[FileDict]]


class LLMAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationale: StrictStr = Field(
        ...,
        description="1-2 sentence high-level reason for your next step. Do NOT reveal steps or chain-of-thought."
    )

    # Can be None if final_answer exists
    actions: Optional[List[Action]] = Field(
        default=None,
        description="the actions you want to take"
    )

    # None if not ready, string if ready
    final_answer: Optional[FinalAnswer] = Field(
        default=None,
        description="the final answer to return if ready, otherwise None")

    @model_validator(mode="after")
    def _validate_actions_vs_final_answer(self) -> "ModelResponse":
        # If we are ready to answer, actions may be None or empty.
        if self.final_answer is not None:
            return self

        # Otherwise (final_answer is None), we must have at least one action.
        if not self.actions or len(self.actions) == 0:
            raise ValueError("actions must be a non-empty list when final_answer is null.")
        return self


from ollama import chat
from ollama import ChatResponse

def parse_first_json_object(s: str):
    s = s.lstrip()
    obj, _ = json.JSONDecoder().raw_decode(s)  # ignores trailing junk
    return obj

@dataclass
class AgentToDoAutonomousOllama:
    system: str = ""

    def __post_init__(self):
        self.messages = []
        if self.system:
            self.messages.append({"role": "system", "content": self.system})
    
    


    def __call__(self, message: str,):
        self.messages.append({"role": "user", "content": message})
        result_obj = self.execute()
        # Store assistant JSON string to keep conversation state consistent
        self.messages.append({"role": "assistant", "content": json.dumps(result_obj)})
        return result_obj
    
    def get_next_step(self, message):
        self.messages.append({"role": "user", "content": message})

        #plan_message = f"""This is your current plan: {todo_list} 
        #"""
        #if this is called after first initial user task, when "next_step" is really a tool call result
        #it needs to dynamically decide whether to add it's appearance as a param here, as "user" role, or "tool" role
        if "tool" in message:
            print("🛠️ the next_step passed to get_next_step is the result of a tool call! 🛠️")

        #self.messages.append({"role": "user", "content": plan_message })
        
        ##try using cohere through openai chat sdk 
        #completion = clientCohere.beta.chat.completions.parse(
            #model="command-a-03-2025",
           # messages=self.messages,
            #response_format=LLMAgentResponse
        #)
        def to_gemini_contents(messages):
            contents = []
            for m in messages:
                role = m["role"]
                text = m["content"]
                
                if role == "system":
                # Gemini expects system instructions via config, not in contents
                    continue
                
                gem_role = "user" if role == "user" else "model"
                contents.append(types.Content(role=gem_role, parts=[types.Part(text=text)]))
            return contents

        system_text = next(m["content"] for m in local_messages if m["role"] == "system")
        contents = to_gemini_contents(local_messages)

        
        
        response = clientGemini.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0,
                system_instruction=system_text,
                response_mime_type="application/json",
                )
            )

        answer = response.text
        filtered_answer = parse_first_json_object(answer)
        formatted_answer = LLMAgentResponse.model_validate(filtered_answer)
        formatted_answer = formatted_answer.model_dump()
        print(f"formatted_answer is: {formatted_answer}")
        self.messages.append({"role": "assistant", "content": json.dumps(formatted_answer)})
        return formatted_answer

        response: ChatResponse = chat(
            model='qwen2.5:0.5b', 
            messages=self.messages, 
            format=LLMAgentResponse.model_json_schema()
            )
        #response = co.chat(
            #messages=self.messages,
            #temperature=0.3,
            #model="command-a-03-2025",
            #)

        #text = response
        #print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")

        #force it into pydantic model
        obj = response["message"]["content"]
        print(f"response obj is: {obj}")
        #obj["tokens_used"] = 1

        step = LLMAgentResponse.model_validate(json.loads(obj))

        print(f"step response is: {step}")
        step = step.model_dump()

        #print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        
        # Minimal validation
        
        
        self.messages.append({"role": "assistant", "content": json.dumps(step)})
        return step
    
    def review_todo_after_action(self, todo_list, action_result):
        messages = self.messages
        messages.append({"role": "user", "content": action_result})

        prompt_messages = f"""Youve just taken a new action, so your action list is now: {messages} 
        
        Your existing plan before the latest step is:  {todo_list}.

        return your updated version of the plan, which can have changes or be the same. Your updated json version must adhere to this format: {ToDoList.model_json_schema()}
        
        """
        print(f"prompt_messages for new todo list: {prompt_messages}")

        completion = client.chat.completions.parse(
            model="gpt-4o",
            temperature=0,
            response_format=ToDoList,  # force JSON you can parse
            messages=[{"role": "user", "content": prompt_messages}],
        )
        text = completion.choices[0].message.content
        try:
            text = json.loads(text)
            print(f"updated version of the plan: {text}")
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e
    
    def review_todo_after_action_markdown(self, todo_list, action_result):
        messages = self.messages
        messages.append({"role": "user", "content": action_result})

        prompt_messages = f"""Youve just taken a new action, so your action list is now: {messages} 
        
        Your existing plan before the latest step is:  {todo_list}.

        return your updated text version of the plan, which can have changes or be the same.
        
        """
        print(f"prompt_messages for new todo list: {prompt_messages}")

        completion = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[{"role": "user", "content": prompt_messages}],
        )
        text = completion.choices[0].message.content
        try:
            #text = json.loads(text)
            print(f"updated version of the plan: {text}")
            return text
        except Exception as e: 
            raise ValueError(f"Model did not return valid JSON: {text}") from e


    def execute(self) -> dict:



        #response: ChatResponse = chat(
            #model='qwen2.5:0.5b', 
            #messages=self.messages, 
            #format=LLMAgentResponse.model_json_schema()
            #)
        #response = co.chat(
            #messages=self.messages,
            #temperature=0.3,
            #model="command-a-03-2025",
            #)

        #text = response
        #print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        def to_gemini_contents(messages):
            contents = []
            for m in messages:
                role = m["role"]
                text = m["content"]
                
                if role == "system":
                # Gemini expects system instructions via config, not in contents
                    continue
                
                gem_role = "user" if role == "user" else "model"
                contents.append(types.Content(role=gem_role, parts=[types.Part(text=text)]))
            return contents

        system_text = next(m["content"] for m in self.messages if m["role"] == "system")
        contents = to_gemini_contents(self.messages)
        
        response = clientGemini.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=1,
                system_instruction=system_text,
                response_mime_type="application/json"
                )
            )

        answer = response.text
        formatted_answer = LLMAgentResponse.model_validate_json(answer)
        formatted_answer = formatted_answer.model_dump()
        print(f"formatted_answer is: {formatted_answer}")
        self.messages.append({"role": "assistant", "content": json.dumps(formatted_answer)})
        return formatted_answer

        #force it into pydantic model
        obj = response["message"]["content"]
        print(f"response obj is: {obj}")
        #obj["tokens_used"] = 1

        #print(f"completion.usage.total_tokens: {completion.usage.total_tokens}")
        step = LLMAgentResponse.model_validate(json.loads(obj))
        print(f"step response is: {step}")
        step = step.model_dump()

        
        
        self.messages.append({"role": "assistant", "content": json.dumps(step)})
        return step








##you should consider doing SFT, using a dataset of user question, and system and assistant calls, like how my agent works
##to see if youc an successfuly fien-tine a model to get better at calls

#could change the outer queryAgentAutonomousTodoListAutomatedTools itself into a object
##need to give them names, either way, and apss name to system prompt

#maybe add instruction to system prompt, not to return state as a argument for functions being called
#so if it is an issue that occurs, could be solved by ensuring state is never returned as a param
#or could just avoid adding state to params in description string of function
#or build params entirely from description string of function, and not use params from signature.inspect


##for concurrent sub_agents, needs acces to state, a list fo sub_agent names from LLM, but also the dynamic sub_agents and their tools
#which is used to pass sub_agenst initially on sub_agent cretain - then names chosen and question can be matched against this, to use asyncio concurrent stuff


#new prompt - to add tools to dynamically:

#I'm going to add this function, for multiple_concurrent_sub_agents
#will require it's own custom internal workflow, but that's fine - then mvoe to somewhere above
import asyncio


##just pass this as a normal function
async def multiple_concurrent_sub_agents(state, tasks: list[str]): #don't passs down state, just create a seeprate one for each
    """
    This function allows you to call multiple sub agents at the same time.

    inputs:
        tasks: a list of the tasks you want performed, each sub_agent will perform one. for example, ["find league position of Tottenham Hotspur", "find league position of Leeds United"]
    """
    #nneed someway to get tools of parent

    #for now, hard-code tools available
    tools=[firecrawl_search, run_python, how_to_web_search, edit_todo_list, write_todo_list, read_todo_list, read_file]
    
    MAX_CONCURRENCY = 10
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    TASK_TIMEOUT_S = 90

    async def bounded_run(task: str, agent_name: str, state: CustomState): #only pass down task as a variable name
        state = CustomState() #create new fresh state for each copy
        async with sem:   #system_prompt, and tools
            return await asyncio.wait_for(queryAgentAutonomousTodoListAutomatedToolsOllama(agent_name, task, state, system_prompt_programatic_ollama, tools=tools), timeout=TASK_TIMEOUT_S)


    if len(tasks) < MAX_CONCURRENCY:
        # Launch all questions concurrently, but respect MAX_CONCURRENCY

        


        tasks_to_do = [
            asyncio.create_task(bounded_run(task, f"agent {i+1}", state))
            for i, task in enumerate(tasks)
            ]

        results = await asyncio.gather(*tasks_to_do, return_exceptions=True)
        print(f"results from multipl_concurrent_sub_agents: {results}")

        #append results to state

        return results
    else:
        return f"Max number of concurrent agents possible: {MAX_CONCURRENCY}. You tried - {len(tasks)}, try a lower number of tasks"



from copy import deepcopy

class CustomState:
    def __init__(self):
        self.state = deepcopy(DEFAULT_STATE)  # avoid shared mutable defaults

    def get_state(self):
        return self.state

    def set_state(self, new_state):
        if not isinstance(new_state, dict):
            raise TypeError(f"new_state must be dict, got {type(new_state)}")
        self.state = new_state

    def __getitem__(self, key):
        return self.state[key]

    def __setitem__(self, key, value):
        self.state[key] = value

ollama_state = CustomState()



#from supabase_helpers import save_file_to_supabase, get_supabase_public_path

import uuid

def list_available_skills() -> list[str]:
    skills_root = (Path(__file__).parent / "SKILLS").resolve() # ensures it looks at SKILLS folder
    if not skills_root.exists():
        return []

    return sorted([
        p.name for p in skills_root.iterdir()
        if p.is_dir() and (p / "skill.md").exists()
    ])

import frontmatter

def load_available_skills(available_skills: list):

    root_dir = ((Path(__file__).parent / "SKILLS").resolve())

    skill_descriptions = []
    skill_descriptions.append("Skills: ")

    for i, skill in enumerate(available_skills):
        folder = (root_dir / skill).resolve()
        file = (folder / "skill.md").resolve()
        yaml_contents = frontmatter.load(file)
        metadata = yaml_contents.metadata
        body = yaml_contents.content
        skill_name = metadata.get("name", skill)
        description = metadata.get("description", "No description provided.")

        files = []
        for path in folder.rglob("*"):
            if path.is_file():
                files.append(str(path.relative_to(folder)))

        block = (
            f"{i}. {skill_name}\n"
            f"   Folder: {skill}\n"
            f"   Description: {description}\n"
            f"   Child files: {files}"
        )
        skill_descriptions.append(block)



    prompt_text = "\n".join(skill_descriptions).strip()
    print(f"value of skill_descriptions is:\n{prompt_text}")
    return prompt_text





def read_skill(
    state,
    skill_name: str,
    relative_path: str = "skill.md",
    max_chars: int = 20000
) -> str:
    """
    Read a file inside one skill folder.

    Example:
      read_skill("how_to_write_artist_report_skill")
      read_skill("how_to_write_artist_report_skill", "report_examples/example1.md")
    """

    print("⚡read_skill was called!")

    # Reject URLs
    parsed = urlparse(relative_path)
    if parsed.scheme in ("http", "https"):
        return (
            f"❌ read_skill only reads LOCAL files. You passed a URL: {relative_path}\n"
            f"Use a web tool to read web pages."
        )

    skills_root = (Path(__file__).parent / "SKILLS").resolve()
    skill_root = (skills_root / skill_name).resolve()

    try:
        skill_root.relative_to(skills_root)
    except ValueError:
        return f"❌ Invalid skill name: {skill_name}"

    if not skill_root.exists() or not skill_root.is_dir():
        return f"❌ Skill folder not found: {skill_name}"

    target_path = (skill_root / relative_path).resolve()

    try:
        target_path.relative_to(skill_root)
    except ValueError:
        return f"❌ Invalid path. You cannot read outside the skill folder: {relative_path}"

    if not target_path.exists():
        return f"❌ File not found: {skill_name}/{relative_path}"
    if not target_path.is_file():
        return f"❌ Path is not a file: {skill_name}/{relative_path}"

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ Failed to read file '{skill_name}/{relative_path}': {e}"

    return content[:max_chars]




def load_mcp_file():
    imported_base_directory = Path.cwd()
    mcp_file = imported_base_directory / "mcp.json"

    if mcp_file.exists():
        if not mcp_file.is_file():
            return None
        try:
            with open(mcp_file, "r", encoding="utf-8") as f:
                mcp_config = json.load(f)

                print("Loaded config:", mcp_config)
                if not isinstance(mcp_config, dict):
                    raise ValueError("mcp.json must contain a JSON object")
                    return None
                    
                return mcp_config

        except json.JSONDecodeError as e:
            print(f"Invalid JSON in mcp.json: {e}")
            return None
    return None


system_prompt_programatic_ollama = f"""
You are a tool-using assistant that works in a loop of (Rationale → Action → Observation) 
until you can provide a final answer.

You can choose one, or multiple, or no functions or agents to call. if a function's params are None, then strictly return None
If you choose to return final_answer, then "actions" should be empty.

*NEVER PASS A *state* VALUE* - exclude it from the params you return (the state will be added automatically, you don't need to give it)

You can choose whether to create a "todo list" for more complex tasks. Your tools to write and save a todo list, read it later,
or edit it can be found under the *todo list functions* section. Any todo list you create should follow this pattern: use numbered point *(1), (2),* (for example)
and each step should be marked as one of "pending" or "in-progress" or "done". Make sure to update the progress of all steps before returning your final answer.


If you want to execute code, the best way is to write the code to a file (write_file function), and then run the file using run_python function, passing the filename

If you aren't certain how to achieve a task, you can get specific instructions by calling one of the "skill" functions.

*Never try and interact with logic.py file - this is your brain, you must not interact with it or touch it.

*Task guidance*
 - You must update your progress as you progress through the task. All steps must be marked as 'done' before you can return a final answer.
 - You can achieve that by calling 'edit_todo_list', and updating all the steps to be marked as 'done'. 
 - some tasks may be date-sensitive - the current date is: {date.today()}

OUTPUT FORMAT (MUST FOLLOW EXACTLY):


This schema: {LLMAgentResponse.model_json_schema()}

TOOL NAME RULES (IMPORTANT):
- You MUST choose action.name ONLY from the allowed list below.
- Never invent tool/agent names.
- If you output an unknown name, your output is invalid.

FINAL_ANSWER RULES (IMPORTANT):
- files is an optional part you can return, if you created any files as part of the answer, which form part of the answer.
- each file needs to be the file name



** Skills **


If any skills exist, you can read a skill by calling the 'read_skill' function with the relative path name to read a specific file within the folder of the skill.


Rules:
- Keep "rationale" brief and non-enumerated (no step-by-step).
- Your final answer should be text - don't try and return markdown or complex table, just answer whatever the user's query was
- If you know the answer now, set "final_answer" and use "no_action" with empty input.
- If you need to use a tool, set "action" to that tool and provide "action_input". Leave "final_answer" as null.
- Never include additional keys. The entire message MUST be valid JSON.
""".strip()


from cerebras.cloud.sdk import Cerebras

client = Cerebras(
    api_key=os.environ.get("CEREBRAS_API_KEY")
)


@dataclass
class Agent:
    system_prompt: None

    def __init__(self, game_id, system_prompt, execute_tool_call_ws, tool_call_results_queue, tools_schema, llm_provider = "Ollama"):
        self.system_prompt = []
        #self.messages_memory = []
        #self.name = name
        self.allow_another_tool_call_cycle = False
        #self.state = state
        self.known_tools_for_agent = {}
        self.known_mcp_tools_for_agent = {}
        self.known_sub_agents = {}
        #self.state["name"] = name
        self.messages = []
        self.execute_tool_call_ws = execute_tool_call_ws
        self.tools_schema = tools_schema
        self.turn_count = 0
        self.tool_call_results_queue = tool_call_results_queue
        self.game_id = game_id
        self.llm_provider = llm_provider

        
        
        final_system_prompt = f"You are a tic-tac-toe playing-agent \n\n" + system_prompt + "*Functions available*: " + json.dumps(self.tools_schema) #need to see what this looks like
        self.system_prompt = final_system_prompt

        print(f"system_prompt_programatic looks like: {final_system_prompt}")

        available_skills = list_available_skills() # always looks for SKILLS folder as sibling to current file
        print(f"available_skills are: {available_skills}")

        ## then fetch description of skill from main skill.md file.
        if available_skills:
            print("available_skills were found - adding skills.. ")
            skill_descriptions = load_available_skills(available_skills)
            final_system_prompt += skill_descriptions
        else:
            print("no available_skills were found - skipping adding skills.. ")

        
        
        
        
        
        
        ## need to add tools, mcp, skills, and stuff to system_prompt, before setting it below
        self.system_prompt = {"role": "system", "content": final_system_prompt}
    
    

    
    
    

    async def get_next_step(self): ## rename to execute?
        # get internal messages + system_prompt, for context to pass down
        print(f"[agent:{self.game_id}] requesting next tool call from model")
        print(f"[agent:{self.game_id}] message_count={len(self.messages)} tools_count={len(self.tools_schema) if self.tools_schema is not None else 'None'}")
        
        if self.llm_provider == "Cerebras":

            ## do tools need formatting for cerebras, compared to ollama?

            completion = client.chat.completions.create(
                messages=[self.system_prompt] + self.messages,
                model="qwen-3.8-27b",
                reasoning_effort="medium",
                tools=self.tools_schema,
                tool_choice="required",
                parallel_tool_calls=False
            )

            print(completion.choices[0].message.content)

            self.messages.append(completion.choices[0].message.model_dump())

            tool_calls = completion.choices[0].message.tool_calls or []
            print(f"[agent:{self.game_id}] parsed tool_calls={tool_calls}")
            return tool_calls

        else:

            response: ChatResponse = chat(
                model='gemma4:e4b', 
                messages=[self.system_prompt] + self.messages, 
                tools=self.tools_schema,
                )
            print(f"[agent:{self.game_id}] raw model response={response}")
        

        #force it into pydantic model
       # obj = response["message"]["content"]
        #print(f"response obj is: {obj}")
        

        #step = LLMAgentResponse.model_validate_json(obj)

        #print(f"step response is: {step}")
        #step = step.model_dump()
        tool_calls = response.message.tool_calls or []
        print(f"[agent:{self.game_id}] parsed tool_calls={tool_calls}")
        return tool_calls

        
        
        
        self.messages.append({"role": "assistant", "content": json.dumps(step)})
        return step
    

    async def generate_response(self, new_game_state):
        print(f"[agent:{self.game_id}] generate_response started new_game_state={new_game_state}")

        ## could add some intermediate bit to make sure LLM focuses on what is issue being asked
        ## but might cause problems with multiple 'user' messages

        
        
        
    
        ## need to ensure it only changes 
        while self.turn_count == 0 or self.turn_count > 0 and self.allow_another_tool_call_cycle == True:
            print(f"🔄Starting Cycle {self.turn_count + 1}🔄")

            self.messages.append({ "role": "user", "content": f"The user has taken their turn. This is the new game state after their turn: {new_game_state}"})
            tool_calls = await self.get_next_step() #in todo version, you need to give todo list in every call, to agent can see it. but dont save it in self
            #when todo list is comleted, it should then choose to return final answer naturally
            #tokens_used += step["tokens_used"]
            # Show the concise rationale each turn
            #print(f"Reasoning: {step['rationale']}")
            self.turn_count += 1
            print(f"agent choice from step {self.turn_count} is {tool_calls}")

            if not tool_calls:
                print(f"[agent:{self.game_id}] no tool calls returned; allowing retry")
                self.messages.append({
                    "role": "user",
                    "content": "You must choose one valid move tool call. Do not answer in text."
                })
                self.allow_another_tool_call_cycle = True
                continue
            

            tool_call = tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = tool_call.function.arguments
            print(f"[agent:{self.game_id}] selected tool_call name={tool_name} args={tool_args}")

            if self.llm_provider == "Cerebras":
                if isinstance(tool_args, str):
                    tool_args = json.loads(tool_args)

            if tool_call.id:
                tool_call_id = tool_call.id
            else:
                tool_call_id = str(uuid.uuid4())

            
            
                        
            future = asyncio.Future()
            print(f"[agent:{self.game_id}] sending agent_tool_call tool_call_id={tool_call_id} name={tool_name} args={tool_args}")
            self.tool_call_results_queue[tool_call_id] = future
            await self.execute_tool_call_ws.send(json.dumps({ "message_type": "agent_tool_call", "tool_call_id": tool_call_id, "tool_call_name": tool_name, "tool_call_arguments": tool_args, "tool_call_arguments_exist": True }))
            print(f"[agent:{self.game_id}] waiting for frontend tool result tool_call_id={tool_call_id}; pending_ids={list(self.tool_call_results_queue.keys())}")
            tool_result = await future
            print(f"[agent:{self.game_id}] received frontend tool result tool_call_id={tool_call_id} result={tool_result}")
                                
            if not tool_result["ok"]:
            ## tool failed, must try again
                print(f"[agent:{self.game_id}] tool result failed; retrying. result={tool_result}")
                print(f"Action: {tool_call}: {tool_args} \nObservation: {tool_result}")
                result_message = f"Action: {tool_name}: {tool_args} \nObservation: {tool_result}\n"
                self.allow_another_tool_call_cycle = True
                self.messages.append({ "role": "tool", "tool_call_id": tool_call_id, "content": result_message })
                continue
            else:
                ## move worked fine - so return
                print(f"[agent:{self.game_id}] tool result ok; completing agent turn")
                print(f"Action: {tool_name}: {tool_args} \nObservation: {tool_result}")
                result_message = f"Action: {tool_call}: {tool_args} \nObservation: {tool_result}\n"
                self.messages.append({ "role": "tool", "tool_call_id": tool_call_id, "content": result_message })
                self.turn_count = 0
                self.allow_another_tool_call_cycle = False 
                return { "turn_successful": True }
                                    

                                                                    
                                
                                
                   

                    
                    
          
            

        

        #need to return udated todo list, but dont add next inut to messages, as that will be done above

        #udate to do list by assing it to new method of agent, that doesnt add todo list to self.messages but does combine them for agent to assess
        #whether comoleted, without saving this snashot
        #would go to new agent method, that adds nextinut on to of existing messages, and todo list, and asks for udated todo list back
        #then arse returned stuff inside that method, and take resonse here and udate todo list to equal that

    
        return "Answer: (no answer within allotted cycles): tokens used:"

        # for core agent loop, just pull messages_memory from parent weboskcet loop eahc time? 
        

    ## uses messages_memory for everything after system_prompt - (tool additions and everything will be added to system_prompt)
    
    

   





     
    
