#!/usr/bin/env python3
"""
Téléchargement des rapports financiers AMMC
"""

import os
import requests
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Structure des documents AMMC
AMMC_DOCUMENTS = [
    {
        "company": "Wafa Assurance",
        "sector": "Assurance",
        "year": 2025,
        "url": "https://www.ammc.ma/sites/default/files/Wafa_Assurance_RFA_2025.pdf",
        "filename": "Wafa_Assurance_RFA_2025.pdf",
        "document_type": "annual_report",
        "description": "Rapport financier annuel Wafa Assurance 2025"
    },
    {
        "company": "CDG Capital",
        "sector": "Finance",
        "year": 2024,
        "url": "https://www.ammc.ma/sites/default/files/CDG_Capital_RFA_2024.pdf",
        "filename": "CDG_Capital_RFA_2024.pdf",
        "document_type": "annual_report",
        "description": "Rapport financier annuel CDG Capital 2024"
    },
    {
        "company": "Unimer",
        "sector": "Agroalimentaire",
        "year": 2024,
        "url": "https://www.ammc.ma/sites/default/files/UNIMER_RFA_2024.pdf",
        "filename": "UNIMER_RFA_2024.pdf",
        "document_type": "annual_report",
        "description": "Rapport financier annuel Unimer 2024"
    },
    {
        "company": "Auto Nejma",
        "sector": "Automobile",
        "year": 2023,
        "url": "https://www.ammc.ma/sites/default/files/Auto_Nejma_RFA_2023.pdf",
        "filename": "Auto_Nejma_RFA_2023.pdf",
        "document_type": "annual_report",
        "description": "Rapport financier annuel Auto Nejma 2023"
    }
]

def setup_directories():
    """Crée la structure de dossiers nécessaire"""
    base_dir = Path("data/raw")
    
    for doc in AMMC_DOCUMENTS:
        # Créer le dossier par secteur et entreprise
        sector_dir = base_dir / doc["sector"].lower().replace(" ", "_")
        company_dir = sector_dir / doc["company"].replace(" ", "_")
        company_dir.mkdir(parents=True, exist_ok=True)
        
        # Créer le dossier metadata
        metadata_dir = company_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Structure de dossiers créée")
    return base_dir

def download_pdf(url: str, output_path: Path, company: str, year: int) -> Optional[Dict]:
    """Télécharge un PDF avec gestion d'erreurs"""
    try:
        logger.info(f"Téléchargement de {company} ({year})...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/pdf',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        }
        
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        content = response.content
        file_size = len(content) / (1024 * 1024)
        file_hash = hashlib.sha256(content).hexdigest()
        
        output_path.write_bytes(content)
        
        logger.info(f"Téléchargé: {output_path.name} ({file_size:.2f} MB)")
        
        return {
            "file_path": str(output_path),
            "file_name": output_path.name,
            "file_size": file_size,
            "file_hash": file_hash,
            "downloaded_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur téléchargement {company}: {str(e)}")
        return None

def save_metadata(company: str, year: int, metadata: Dict):
    """Sauvegarde les métadonnées du document"""
    company_dir = Path(f"data/raw/{metadata['sector'].lower().replace(' ', '_')}/{company.replace(' ', '_')}")
    metadata_file = company_dir / "metadata" / f"metadata_{year}.json"
    
    metadata.update({
        "company": company,
        "year": year,
        "processed_at": datetime.utcnow().isoformat(),
        "status": "downloaded"
    })
    
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Métadonnées sauvegardées pour {company} ({year})")

def download_all_reports():
    """Télécharge tous les rapports en parallèle"""
    setup_directories()
    
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        
        for doc in AMMC_DOCUMENTS:
            sector_dir = Path(f"data/raw/{doc['sector'].lower().replace(' ', '_')}")
            company_dir = sector_dir / doc["company"].replace(" ", "_")
            output_path = company_dir / doc["filename"]
            
            future = executor.submit(
                download_pdf,
                doc["url"],
                output_path,
                doc["company"],
                doc["year"]
            )
            futures[future] = doc
        
        for future in as_completed(futures):
            doc = futures[future]
            result = future.result()
            
            if result:
                result.update({
                    "sector": doc["sector"],
                    "company": doc["company"],
                    "year": doc["year"],
                    "document_type": doc["document_type"],
                    "description": doc["description"],
                    "url": doc["url"]
                })
                
                save_metadata(doc["company"], doc["year"], result)
                results.append(result)
    
    logger.info("\n" + "="*50)
    logger.info("RÉSUMÉ DU TÉLÉCHARGEMENT")
    logger.info("="*50)
    logger.info(f"Total: {len(AMMC_DOCUMENTS)} documents")
    logger.info(f"Réussis: {len(results)}")
    logger.info(f"Échoués: {len(AMMC_DOCUMENTS) - len(results)}")
    
    summary = {
        "download_date": datetime.utcnow().isoformat(),
        "total_documents": len(AMMC_DOCUMENTS),
        "successful": len(results),
        "documents": results
    }
    
    with open("data/raw/download_summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    return results

if __name__ == "__main__":
    print("Téléchargement des rapports AMMC")
    print("="*50)
    download_all_reports()
