"""Langflow component to detect missing fields in a contract and fill them."""

import re
from datetime import datetime
from pathlib import Path

from langflow.custom import Component
from langflow.io import MessageTextInput, Output, StrInput
from langflow.schema.message import Message


class ContractFiller(Component):
    display_name = "Contract Filler"
    description = (
        "Detects blank fields in a contract template, prompts user for missing info, "
        "fills them in, and saves the completed contract to /app/openrag-documents."
    )
    icon = "file-text"

    inputs = [
        MessageTextInput(
            name="contract_text",
            display_name="Contract Text",
            info="The raw contract text retrieved from knowledgebase.",
            required=True,
        ),
        MessageTextInput(
            name="user_data",
            display_name="User Provided Data (JSON or key:value lines)",
            info='Provide field values as JSON {"field": "value"} or "field: value" lines. Leave empty to get the list of missing fields.',
            required=False,
        ),
        StrInput(
            name="output_filename",
            display_name="Output Filename (optional)",
            info="Custom filename without extension.",
            required=False,
        ),
    ]

    outputs = [
        Output(display_name="Result", name="output", method="process_contract"),
    ]

    # Patterns that indicate a blank field in a contract template
    BLANK_PATTERNS = [
        r"\[([^\]]+)\]",          # [Field Name]
        r"\{([^\}]+)\}",          # {Field Name}
        r"_{3,}",                  # ___ (3+ underscores)
        r"\.{3,}",                 # ... (3+ dots)
        r"<([^>]+)>",             # <Field Name>
    ]

    def _extract_fields(self, text: str) -> list[str]:
        """Extract named blank fields from contract text."""
        fields = []
        for pattern in self.BLANK_PATTERNS[:2] + self.BLANK_PATTERNS[3:]:  # skip ___ and ...
            matches = re.findall(pattern, text)
            fields.extend(m.strip() for m in matches if m.strip())
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for f in fields:
            if f.lower() not in seen:
                seen.add(f.lower())
                unique.append(f)
        return unique

    def _parse_user_data(self, raw: str) -> dict[str, str]:
        """Parse user-provided data from JSON or key:value lines."""
        if not raw or not raw.strip():
            return {}
        raw = raw.strip()
        # Try JSON first
        if raw.startswith("{"):
            import json
            try:
                return json.loads(raw)
            except Exception:
                pass
        # Fall back to key: value lines
        result = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
        return result

    def _fill_contract(self, text: str, data: dict[str, str]) -> str:
        """Replace blank fields with provided values."""
        for field, value in data.items():
            # Replace [field], {field}, <field> (case-insensitive)
            for tmpl in [f"[{field}]", f"{{{field}}}", f"<{field}>"]:
                text = re.sub(re.escape(tmpl), value, text, flags=re.IGNORECASE)
        return text

    def process_contract(self) -> Message:
        contract = (
            self.contract_text
            if isinstance(self.contract_text, str)
            else self.contract_text.text
        )
        raw_data = (
            self.user_data
            if isinstance(self.user_data, str)
            else (self.user_data.text if self.user_data else "")
        ) or ""

        missing_fields = self._extract_fields(contract)
        user_data = self._parse_user_data(raw_data)

        # Determine which fields are still missing
        still_missing = [
            f for f in missing_fields
            if f.lower() not in {k.lower() for k in user_data}
        ]

        if still_missing:
            prompt = (
                "Hợp đồng có các trường chưa được điền. "
                "Vui lòng cung cấp thông tin cho các trường sau:\n\n"
                + "\n".join(f"- {f}" for f in still_missing)
                + "\n\nBạn có thể trả lời theo định dạng:\n"
                + "\n".join(f"{f}: <giá trị>" for f in still_missing)
            )
            return Message(text=prompt)

        # All fields provided — fill and save
        filled = self._fill_contract(contract, user_data)

        output_dir = Path("/app/openrag-documents")
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = (self.output_filename or "").strip()
        if not filename:
            filename = f"contract_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)

        file_path = output_dir / f"{filename}.txt"
        counter = 1
        while file_path.exists():
            file_path = output_dir / f"{filename}_{counter}.txt"
            counter += 1

        file_path.write_text(filled, encoding="utf-8")
        self.log(f"Contract saved to {file_path}")

        return Message(
            text=f"✅ Hợp đồng đã được điền đầy đủ và lưu tại: `{file_path.name}`\n\n---\n\n{filled}"
        )
