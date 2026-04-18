from fastapi import FastAPI, APIRouter
from backend.app.core.plugin import Plugin

class HelloWorldPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.manifest = {
            "name": "Hello World",
            "version": "0.1",
            "description": "A simple example plugin."
        }
        self.router = APIRouter()

    def on_load(self, app: FastAPI):
        # Define routes
        @self.router.get("/greet")
        async def greet():
            return {"message": "Hello from Plugin!"}
        
        # Register router
        app.include_router(self.router, prefix="/api/plugins/hello_world", tags=["Plugin: Hello World"])
        print("Hello World Plugin Loaded!")

# Export instance
plugin = HelloWorldPlugin()
