from datetime import datetime
from typing import Dict
import asyncio
import json, re
from metagpt.actions.action_node import ActionNode
from metagpt.const import TUTORIAL_PATH
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message
from metagpt.utils.file import File

from typing import Dict

from metagpt.actions import Action
from metagpt.prompts.tutorial_assistant import DIRECTORY_PROMPT, CONTENT_PROMPT
from metagpt.utils.common import OutputParser

LANGUAGE = ActionNode(
    key="Language",
    expected_type=str,
    instruction="Provide the language used in the project, typically matching the user's requirement language.",
    example="en_us",
)

TOPIC = ActionNode(
    key="Topic",
    expected_type=str,
    instruction="Understand user's requirement and get the Topic user want to learn",
    example=""
)

DIRECTORY = ActionNode(
    key="Directory",
    expected_type=str,
    instruction="""
        Analyze the topic and think what is the reader want to learn from the tutorial based on this topic.
        Then generate the subdirectories based on this topic.
        """,
    example="""
        [subdirectory1, subdirectory2, subdirectory3]
        """
)

CONTENT = ActionNode(
    key="Content",
    expected_type=str,
    instruction="""
        Now I will give you the module directory titles for the topic. 
        Please output the detailed principle content of this title in detail. 
        If there are code examples, please provide them according to standard code specifications. 
        Without a code example, it is not necessary.
        """,
    example="""
        1. subdirectory1: xxxxx
        """
)

UNDERSTAND_REQUIREMENT = ActionNode.from_children("Understand Requirement", [LANGUAGE, TOPIC])
WRITE_DIRECTORY = ActionNode.from_children("Write Directory", [DIRECTORY])
WRITE_CONTENT = ActionNode.from_children("Write Content", [CONTENT])

class UnderstandRequirement(Action):
    def __init__(self, name: str = "", *args, **kwargs):
        super().__init__()
        self.node = UNDERSTAND_REQUIREMENT


class WriteDirectoryInAN(Action):
    def __init__(self, name: str = "", *args, **kwargs):
        super().__init__()
        self.node = WRITE_DIRECTORY

class WriteContentInAN(Action):
    directory:str = ""

    def __init__(self, directory: str = "", *args, **kwargs):
        super().__init__()
        self.directory = directory
        self.node = WRITE_CONTENT

    async def run(self, *args, **kwargs):
        msgs = args[0]
        context = "## History Messages\n"
        context += "\n".join([f"{idx}: {i}" for idx, i in enumerate(reversed(msgs))])
        context += "\n".join(self.dictory)
        return await self.node.fill(context=context, llm=self.llm)

class TutorialAssistantAN(Role):
    directories_nodes: list[ActionNode] = []

    def __init__(
            self,
            name: str = "Stitch",
            profile: str = "Tutorial Assistant",
            goal: str = "Generate tutorial documents",
            constraints: str = "Strictly follow Markdown's syntax, with neat and standardized layout",
    ):
        super().__init__()
        self.name = name
        self.profile = profile
        self.goal = goal
        self.constraints = constraints

        self._set_react_mode("by_order")
        self._init_actions([UnderstandRequirement, WriteDirectoryInAN])

    async def _act(self) -> Message:
        """Perform an action as determined by the role.

        Returns:
            A message containing the result of the action.
        """
        todo = self.rc.todo
        if type(todo) is UnderstandRequirement:
            resp = await todo.run(self.rc.history)

        if type(todo) is WriteDirectoryInAN:
            resp = await todo.run(self.rc.history)
            directories = await self._handle_directory(resp.content)

            for directory in directories:
                logger.info(directory)
                self.directories_nodes.append(WriteContentInAN(directory=directory))

            self.init_actions(self.directories_nodes)
            return resp

        resp = await todo.run(self.rc.history)

        msg = Message(
            content=resp.content,
            instruct_content=resp.instruct_content,
            role=self.profile,
            cause_by=self.rc.todo,
            sent_from=self,
        )
        self.rc.memory.add(msg)

        return msg

    async def _handle_directory(self, string: str) -> list:
        """Handle the content, and extract the directory"""
        pattern = r"\[CONTENT\](.*?)\[\/CONTENT\]"
        match = re.search(pattern, string, re.DOTALL)  # re.DOTALL 允许 . 匹配任何字符，包括换行符
        if match:
            extracted_content = match.group(1).strip()
            data = json.loads(extracted_content)
            directory_string = data["Directory"].strip()
            pattern = r"\[(.*?)\]"
            match = re.search(pattern, directory_string)
            if match:
                list_items = match.group(1).split(", ")
                return list_items

        return []

async def main():
    msg = "请帮我写一篇关于 Git 的教程"
    role = TutorialAssistantAN()
    logger.info(msg)
    result = await role.run(msg)
    logger.info(result)

asyncio.run(main())