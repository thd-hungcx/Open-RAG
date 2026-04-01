"""Custom Langflow component to save agent response to a .txt file."""

from datetime import datetime
from pathlib import Path

from langflow.custom import Component
from langflow.io import MessageTextInput, Output, StrInput
from langflow.schema.message import Message


class SaveResponseToFile(Component):
    display_name = "Save Response to File"
    description = "Saves the agent response to a .txt file in /app/openrag-documents."
    icon = "file-text"

    inputs = [
        MessageTextInput(name="response", display_name="Response", required=True),
        StrInput(
            name="filename",
            display_name="Filename (optional)",
            info="Custom filename without extension. Defaults to timestamp.",
            required=False,
        ),
    ]

    outputs = [
        Output(display_name="Response", name="output", method="save_and_pass"),
    ]

    def save_and_pass(self) -> Message:
        text = self.response if isinstance(self.response, str) else self.response.text
        filename = (self.filename or "").strip()

        output_dir = Path("/app/openrag-documents")
        output_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            filename = f"response_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)
        file_path = output_dir / f"{filename}.txt"

        counter = 1
        while file_path.exists():
            file_path = output_dir / f"{filename}_{counter}.txt"
            counter += 1

        file_path.write_text(text, encoding="utf-8")
        self.log(f"Response saved to {file_path}")

        return Message(text=text)
