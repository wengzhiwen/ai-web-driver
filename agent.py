from browser_use import Agent
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
        base_url=os.getenv("BASE_URL")
    )
    
    # 定义任务
    task = "访问 https://xxxx.com/ 进入客服中心（注意，客服中心可能会以新tab的方式被打开），在客服中心页面上找到客服QQ，确认客服QQ为444444或555555"
    
    # 创建Agent
    agent = Agent(task=task, llm=llm, use_vision=False)
    
    # 运行Agent
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
