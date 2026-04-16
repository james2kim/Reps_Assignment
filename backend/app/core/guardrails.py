"""
Guardrail responses — exact text from the spec.

1. Out-of-scope: unrelated to job or assigned materials
2. General professional: sales techniques not in assigned plays (LLM answers + disclaimer)
3. Proprietary ungrounded: specific company data with no grounding
"""

# 1. Search Boundary (Out-of-Scope)
OUT_OF_SCOPE_RESPONSE = (
    "I am a specialized search engine for your assigned Reps materials. "
    "I cannot assist with queries outside of your professional scope."
)

# 2. General Professional Knowledge — disclaimer appended to LLM answer
GENERAL_PROFESSIONAL_DISCLAIMER = (
    "This response is based on general sales knowledge and is not found "
    "in your assigned company materials."
)

# 3. Proprietary Data Guardrail (No Hallucination)
PROPRIETARY_UNGROUNDED_RESPONSE = (
    "I cannot find any specific information in your assigned materials regarding this query."
)

# Fallback when assigned_search retrieval returns no relevant results
NO_RESULTS_RESPONSE = (
    "I cannot find any specific information in your assigned materials regarding this query."
)
