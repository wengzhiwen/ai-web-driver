from browser_use import Agent, Browser
from browser_use.llm import ChatOpenAI
import asyncio
import os
from dotenv import load_dotenv


async def main():
    # 加载环境变量
    load_dotenv()

    # 配置OpenAI兼容的LLM
    llm = ChatOpenAI(
        model=os.getenv("MODEL_STD", "glm-4-flash"),  # 使用智谱AI的模型
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"))

    # 配置页面内容提取的轻量级LLM
    page_extraction_llm = ChatOpenAI(
        model=os.getenv("MODEL_MINI", "glm-4.5-air"),  # 使用智谱AI的轻量模型
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"))

    # 配置浏览器基本模式
    browser = Browser(
        headless=False,  # 显示浏览器窗口
        window_size={
            'width': 1920,
            'height': 1080
        },  # 设置为1080p横向尺寸
    )

    # 定义任务
    task = "访问 https://bigmodel.cn/ 进入关于页面（我不确定关于页面的准确入口名称），在关于页面中确认联系邮箱是是否是service@zhipuai.cn"

    # 创建Agent，传入配置好的浏览器
    agent = Agent(task=task, llm=llm, page_extraction_llm=page_extraction_llm, browser=browser, use_vision=False)

    # 运行Agent
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
