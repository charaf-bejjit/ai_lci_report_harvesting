# AI-based Framework for LCI Data Extraction from Company Reports

## Overview

This project implements a semi-automated AI framework to extract Life Cycle Inventory (LCI) data from corporate sustainability and ESG reports in the mining sector.

It addresses the challenge of accessing structured, site-level primary data for Life Cycle Assessment (LCA).

The pipeline is applied to copper (Cu) and nickel (Ni) value chains, with a focus on retrieving site-level production and environmental data.

For full methodological details, please refer to:

* 📄 Article: `docs/Article_Draft_v5.docx`
* 📄 Supplementary Information: `docs/Screening_and_Multimodal_Extraction_SI_document_3.docx`

---

## Workflow

The pipeline is structured in two main steps:

1. **Screening**

   * Identifies reports containing relevant quantitative data
   * Classifies documents as GO / MAYBE / NO-GO

2. **Extraction**

   * Multimodal extraction (text + image)
   * Retrieves structured metrics (production, energy, emissions, etc.)
   * Preserves units, context, and site-level information

---

## Project Structure

```
ai-lci-report-harvesting/
├── src/
│   ├── screening/
│   └── extraction/
├── docs/
│   ├── Article_Draft_v5.docx
│   └── Screening_and_Multimodal_Extraction_SI_document_3.docx
```

---

## Requirements

* Python 3.10+
* pdfplumber
* pandas
* rapidfuzz
* google-cloud-aiplatform
* vertexai
* pillow
* pdf2image
* tqdm
* openpyxl

---

## Notes

* Raw data are not included due to size constraints
* Example outputs can be added if needed
* The pipeline is designed for English-language PDF reports

---

## Author

Charaf Eddine Bejjit  
Data Scientist – Environmental and Social Assessment (2ES)  
Mineral Resources Division (DRM)  
BRGM – French Geological Survey           
