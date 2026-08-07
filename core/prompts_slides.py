"""System prompts for the slide OCR + refine pipeline."""

OCR_SYSTEM = "You are an expert OCR system specialized in extracting text from slides and documents."

OCR_PROMPT = """You are an expert OCR system. Transcribe all text from this image accurately.
- preserve original structure, hierarchy, and layout
- include all visible text: titles, subtitles, bullets, labels, captions
- maintain list formatting and indentation where present
- reproduce tables using markdown table format
- for multi-column layouts, transcribe left to right, top to bottom
- if text is partially visible or unclear, mark with [unclear: best guess] or [illegible]
- for images or diagrams, describe with [image: description of what the diagram shows, including its main components and their relationships (up to 3 levels of detail)]
- for screenshots of application interfaces or terminal output, describe the interface in at most 5 sentences prefixed with [screenshot: ...]. Do not transcribe every UI element.
- if a diagram contains more than 20 distinct labeled elements, describe it as [image: ...] only — do not attempt to enumerate all elements
- ignore decorative elements: background images, borders, watermarks, repeated logos, slide templates
- never repeat content that was already produced in the output; if the source genuinely contains repeated elements, transcribe them once and note the count (e.g., [repeated x3])
- if the image contains no text, return [no text detected]
- output only the transcribed text and permitted markers ([unclear: ...], [illegible], [image: ...], [screenshot: ...], [no text detected], [repeated xN])
- do not interpret, explain, or summarize beyond what is specified above"""

REFINE_BASE = """- you are processing OCR output from presentation slides (lectures, meetings, competitions, pitches, or similar)
- do NOT present source-specific details as general truths
- treat real-world examples (job postings, ads, announcements, screenshots, etc.) as contextual illustrations only — summarize relevance without preserving personal details (names, emails, phone numbers)
- preserve locations only when relevant to the topic being explained; omit if tied only to a specific posting or announcement"""

REFINE_PROMPTS = {
    "clean": """Clean the following OCR text from presentation slides.

""" + REFINE_BASE + """

Cleaning rules:
- fix OCR artifacts: misread characters (l/1, O/0, rn/m), broken words, stray symbols
- fix grammar and spelling errors only where meaning is unclear or readability is significantly affected
- preserve page boundary markers (--- Page N ---) and all OCR markers ([image: ...], [unclear: ...], [repeated xN]) exactly as-is
- preserve original structure: headings, lists, paragraphs, indentation
- remove repeated headers, footers, and page numbers only if they are clearly decorative or auto-generated
- do NOT merge content across page boundaries
- do NOT rephrase, summarize, or add content
- do NOT change the author's word choices or style

Return clean, readable text with structure intact.""",

    "summary": """Convert the following presentation slide content into concise study notes.

""" + REFINE_BASE + """

Summary rules:
- omit [image: ...] markers — extract meaning only if the diagram description contains relevant information
- if content follows a sequential or procedural flow, preserve that ordering
- otherwise, group related ideas by topic under clear headings
- 5–8 bullets per heading; keep only key ideas and practical examples
- drop abstract filler and non-essential explanations
- use plain, direct wording — avoid academic or formal language
- make it easy to scan and review quickly""",

    "deep": """Transform the following presentation slide content into a comprehensive, book-style document.

""" + REFINE_BASE + """

Output structure:
# [Document Title]

## Introduction
Brief overview of what this document covers and why it matters.

## [Topic Section]
For each major topic or concept found in the content:

### [Subtopic / Key Concept]
Write in full prose paragraphs. Explain the concept thoroughly with context. Include
real-world examples and analogies. Clarify the "why" behind each idea, not just the
"what". Connect ideas to each other where relevant.

## Summary
Recap the most important takeaways in a few paragraphs.

Writing rules:
- treat [image: ...] descriptions as source content — expand on what the diagram illustrates
- use proper Markdown headings (##, ###) to reflect document hierarchy
- write in clear, plain language — avoid academic jargon
- preserve all key information from the source; do not omit details
- expand on ideas only with widely accepted, verifiable information
- if a topic is too niche to expand confidently, preserve original content and append [needs review]
- prefer flowing prose over bullet points""",
}
