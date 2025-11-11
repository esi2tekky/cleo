# SSENSE Chatbot Prototype

This repo contains scraping, enrichment, and chatbot logic for a conversational shopping assistant powered by COS product data.

## Folder Structure
- `scraping/`: Web scraping scripts and selectors
- `utils/`: Data cleanup and enrichment tools
- `data/`: Raw and processed datasets
- `notebooks/`: Jupyter notebooks for exploring and testing
- `scripts/`: Helper shell scripts

## Instructions
- Install dependencies: `pip install -r requirements.txt`
- Run scraper: `python scraping/ssense_scraper.py`
- Enrich data: `python utils/enrich.py`
