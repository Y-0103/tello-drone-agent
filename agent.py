import re,json,os,asyncio
from operator import add
from setting import *
from langchain_qwq import ChatQwen
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage,SystemMessage,HumanMessage,AnyMessage
from langgraph.graph import StateGraph,START,END
from typing import TypedDict,List,Annotated
from retriever_doc import retriever
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv


load_dotenv()
llm = ChatQwen(
    model = "qwen-plus-latest",
    api_key = os.getenv("LLM_API_KEY"),
    base_url= os.getenv("LLM_BASE_URL")
)

class State(TypedDict):
    input : str
    history : Annotated[List[HumanMessage],add]
    messages: Annotated[List[AnyMessage],add]
    command : List[str]
    now_command : str
    type : str
    agent_node : str
    error_turning : bool
    real_time_information : int

async def router_node(state: State)->str:
    global CONCURRENCY_NUMBER
    CONCURRENCY_NUMBER += 1
    prompt = NODE_PROMPT
    prompts = [
        SystemMessage(content = prompt),
        HumanMessage(content = state["input"]),
    ]
    response = await llm.ainvoke(prompts)
    return {
        "history": [state["input"]],
        "messages": [state["input"]],
        "agent_node": response.content
    }

def node_turning(state: State)->State:
    return state["agent_node"]

async def chat_node(state: State)->State:
    response_sys = "【切换到聊天模式】：▼"
    prompt = """你是一个聊天大师，负责对用户的要求进行回复。"""
    prompts = [
        SystemMessage(content = prompt),
        HumanMessage(content = state["input"]),
    ]
    response_llm = await llm.ainvoke(prompts)

    response = response_sys + '\n' + response_llm.content
    return {
        "messages": [AIMessage(content = response)],
    }

async def history_node(state: State)->State:
    prompt = f"""你需要根据用户的最新输入:{state["input"]}的语义，
        来捕捉用户的历史输入信息列表：{state["history"]}。
        并返回一个类似于用户的输入str，该输入要求是通过用户的最新输入对用户的历史输入信息进行操作后的结果。
        注意1：信息列表里面每个元素是一条完整的历史指令，无论该指令多长，只要在一个元素内，都是一条指令。
        注意2：如果涉及重复操作，没有明确说明对历史指令进行改动则不要改动历史信息的操作。
        注意3：返回的内容只需要有关无人机的操作指令，其他内容不需要返回。
        """
    prompts = [
        SystemMessage(content=prompt)
    ]
    response = await llm.ainvoke(prompts)
    return {
        "input": response.content
    }

async def split_node(state: State)->State:
    prompt = SPLIT_PROMPT
    prompts = [
        SystemMessage(content=prompt),
        HumanMessage(content=state["input"]),
    ]
    response = await llm.ainvoke(prompts)
    return {
        "command": eval(response.content)
    }

def allocate_node(state: State)->State:
    command = state["command"][0]
    return {
        "input": command
    }

async def operate_message_node(state: State)->State:
    prompt = CLASSIC_PROMPT
    prompts = [
        SystemMessage(content = prompt),
        HumanMessage(content = state["input"]),
    ]
    response = await llm.ainvoke(prompts)
    return {
        "type" :  response.content
    }

async def operate_run_node(state: State)->State:
    prompt = ChatPromptTemplate.from_template(
        """
        从上下文中找到用户输入的指令对应的代码。
        上下文：{context}
        指令：{command}
        注意1：只返回代码，不要添加任何额外文字说明
        注意2：需要严格遵循上下文代码里面的单位，如果用户输入指令中单位与上下文中相关内容的单位不一致，
        需要将输入指令的单位换算成上下文中示例的单位。  
        """
    )
    context = retriever.invoke(state['type'])
    input = prompt.invoke({
        "context": context,
        "command": state["input"],
    })
    response = await llm.ainvoke(input)
    command_list = state["command"][1:]
    return{
        "command": command_list,
        "now_command" : response.content
    }

async def run_timer_node(state: State,config: RunnableConfig)->State:
    now_command = state["now_command"]
    tello = config["configurable"]["tello"]
    if state["type"] == "基础运动类":
        if "move" in now_command:
            speed = re.search(r'\((-?\d+)\)', now_command)
            speed = int(speed.group(1))
            try:
                print(now_command)
                eval("tello." + now_command)
            except Exception as e:

                return{
                   "error_turning": True
                }
            await asyncio.sleep(speed / 100 + 1)
        elif "rotate" in now_command:
            theta = re.search(r'\((-?\d+)\)', now_command)
            theta = float(theta.group(1))
            try:
                print(now_command)
                eval("tello." + now_command)
            except Exception as e:
                return{
                   "error_turning": True
                }
            await asyncio.sleep(theta / 90 + 1)
        else:
            try:
                print(now_command)
                eval("tello." + now_command)
            except Exception as e:
                return{
                   "error_turning": True
                }
            await asyncio.sleep(1)

    elif state['type'] == "实时信息类":
        try:
            print(now_command)
            result = eval("tello." + now_command)
        except Exception as e:
            return {
                "error_turning": True,
            }
        await asyncio.sleep(1)
        return {
            "real_time_information": result
        }

    elif state['type'] == "连续运动流":
        while CONCURRENCY_NUMBER == 1:
            try:
                print(now_command)
                eval("tello." + now_command)
            except Exception as e:
                return {
                    "error_turning": True
                }
            await asyncio.sleep(0.05)
        return{
            "command": [],
        }
    return {
    }

def repeat_run_turning(state: State)->State:
    if state["error_turning"]:
        return "end_node"

    command_list = state["command"]

    if command_list:
        return "allocate_node"
    else:
        return "end_node"

def end_node(state: State)->State:
    global CONCURRENCY_NUMBER
    CONCURRENCY_NUMBER -= 1
    if state["error_turning"]:
        return {
            "error_turning": False,
            "messages": [AIMessage(content=f"当前指令错误或者不完整：{state["now_command"]}")]
        }
    if state["real_time_information"]!= 0:
        return {
            "messages": [AIMessage(content= f"您的指令已完成，当前值为：{state["real_time_information"]}")]
        }

    return{
        "messages": [AIMessage(content="您的指令已完成")],
    }

builder = StateGraph(State)
builder.add_node("router_node",router_node)
builder.add_node("history_node",history_node)
builder.add_node("split_node",split_node)
builder.add_node("allocate_node",allocate_node)
builder.add_node("chat_node",chat_node)
builder.add_node("operate_message_node",operate_message_node)
builder.add_node("operate_run_node",operate_run_node)
builder.add_node("run_timer_node",run_timer_node)
builder.add_node("end_node",end_node)
builder.add_edge(START,"router_node")
builder.add_conditional_edges("router_node",node_turning,
                              {"history_node","split_node","chat_node"})
builder.add_edge("history_node","split_node")
builder.add_edge("split_node","allocate_node")
builder.add_edge("allocate_node","operate_message_node")
builder.add_edge("operate_message_node","operate_run_node")
builder.add_edge("operate_run_node","run_timer_node")
builder.add_conditional_edges("run_timer_node",repeat_run_turning,
                              {"allocate_node","end_node"})
builder.add_edge("chat_node",END)
builder.add_edge("end_node",END)

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

async def main(input,config):
    init_state: State = {
        "input": input,
        "error_turning": False,
        "real_time_information": 0
    }
    response = await graph.ainvoke(init_state,config)
    return response








