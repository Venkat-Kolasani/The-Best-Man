from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_api_key: str = ""
    github_token: str = ""
    cognee_db_path: str = "data/cognee"
    cognee_llm_provider: str = "litellm"
    cognee_llm_model: str = "gemini/gemini-1.5-flash"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
