from __future__ import annotations

import json
from typing import Any

from lfx.io import (
    Data,
    HandleInput,
    MultilineInput,
    Output,
    StrInput,
)
from lfx.log import logger
from flows.components.opensearch_multimodal import OpenSearchVectorStoreComponentMultimodalMultiEmbedding

class DualPathOpenSearchComponent(OpenSearchVectorStoreComponentMultimodalMultiEmbedding):
    display_name = "Dual-Path OpenSearch Search"
    description = "Search documents with departmental security: detailed results for your department, summarized for others."
    
    inputs = OpenSearchVectorStoreComponentMultimodalMultiEmbedding.inputs + [
        StrInput(
            name="user_department",
            display_name="User Department",
            info="The department of the current user (usually linked to {{DEPARTMENT}} global variable).",
            value="",
        ),
        HandleInput(
            name="summarizer_llm",
            display_name="Summarizer LLM",
            info="LLM to use for summarizing results from other departments.",
            input_types=["LanguageModel"],
        ),
        MultilineInput(
            name="summarization_prompt",
            display_name="Summarization Prompt",
            info="Prompt to use for summarizing other departments' data.",
            value="Bạn là một trợ lý bảo mật. Hãy tóm tắt thông tin sau đây một cách tổng quát, không tiết lộ bất kỳ số liệu cụ thể, tên riêng, hoặc chi tiết nhạy cảm nào. Chỉ đưa ra các ý chính chung nhất.",
        )
    ]
    
    outputs = OpenSearchVectorStoreComponentMultimodalMultiEmbedding.outputs

    async def search_documents(self) -> list[Data]:
        import time
        start_time = time.time()
        
        query = self.search_query
        if not query:
            return []

        # 1. Path 1: Internal Search (Same Department)
        internal_filter = {
            "filter": [{"term": {"department": self.user_department}}],
            "limit": self.number_of_results
        }
        self.filter_expression = json.dumps(internal_filter)
        
        s1_start = time.time()
        internal_results = super().search_documents()
        s1_end = time.time()
        logger.info(f"[DualPath] Internal search took {s1_end - s1_start:.2f}s (results: {len(internal_results)})")
        
        # 2. Path 2: Global Search (Other Departments) - Limit to 3 for summarization
        global_limit = 3
        global_filter = {
            "filter": [{"must_not": {"term": {"department": self.user_department}}}],
            "limit": global_limit
        }
        self.filter_expression = json.dumps(global_filter)
        
        s2_start = time.time()
        global_results = super().search_documents()
        s2_end = time.time()
        logger.info(f"[DualPath] Global search took {s2_end - s2_start:.2f}s (results: {len(global_results)})")
        
        # 3. Summarize Global Results
        summarized_global_data = ""
        if global_results:
            combined_global_text = "\n\n".join([d.text for d in global_results])
            
            if self.summarizer_llm:
                prompt = f"{self.summarization_prompt}\n\nDữ liệu cần tóm tắt:\n{combined_global_text}"
                try:
                    sum_start = time.time()
                    summary_resp = await self.summarizer_llm.agenerate([prompt])
                    summarized_global_data = summary_resp.generations[0][0].text
                    sum_end = time.time()
                    logger.info(f"[DualPath] Summarization took {sum_end - sum_start:.2f}s")
                except Exception as e:
                    logger.error(f"Error summarizing global results: {e}")
                    summarized_global_data = "[Lỗi tóm tắt dữ liệu phòng ban khác]"
            else:
                summarized_global_data = "[Thông tin từ phòng ban khác - cần cấu hình LLM để tóm tắt]"

        # 4. Combine
        final_results = []
        for r in internal_results:
            final_results.append(r)
            
        if summarized_global_data:
            summary_node = Data(
                text=f"Tóm tắt thông tin từ các phòng ban khác:\n{summarized_global_data}",
                metadata={"source_type": "Global (Summarized)", "department": "Other"}
            )
            final_results.append(summary_node)
            
        total_end = time.time()
        logger.info(f"[DualPath] Total dual-path process took {total_end - start_time:.2f}s")
        
        return final_results
