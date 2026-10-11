#!/usr/bin/env python3
"""
Script d'ingestion des rapports AMMC - V3
- Conservation de la structure (paragraphes, titres)
- Métadonnées complètes par chunk
- Pages tracées précisément
- Préparation pour la sécurité (classification, rôles)
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import pdfplumber
import re

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentIngestorV3:
    """
    Ingestion des documents AMMC - Version 3
    Avec structure préservée et métadonnées complètes
    """
    
    def __init__(self):
        self.base_path = Path("data/raw")
        self.chunk_size = 1000
        self.chunk_overlap = 150
        self.min_chunk_size = 100
    
    def process_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extraire le texte d'un PDF et créer des chunks avec métadonnées
        """
        try:
            logger.info(f"📄 Traitement de: {pdf_path.name}")
            
            # Extraire les métadonnées du chemin
            company = pdf_path.parent.name.replace("_", " ")
            sector = pdf_path.parent.parent.name.replace("_", " ")
            
            # Extraire l'année du nom de fichier
            year_match = re.search(r'(\d{4})', pdf_path.name)
            year = int(year_match.group(1)) if year_match else None
            
            # Extraction page par page avec conservation de la structure
            pages_content = []
            total_pages = 0
            
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        pages_content.append({
                            "page": page_num,
                            "text": page_text,
                            "char_count": len(page_text)
                        })
                    if page_num % 10 == 0:
                        logger.info(f"  Page {page_num}/{total_pages} traitée")
            
            # Créer des chunks avec métadonnées
            chunks_with_metadata = self._create_chunks_with_metadata(
                pages_content=pages_content,
                company=company,
                sector=sector,
                year=year,
                filename=pdf_path.name,
                total_pages=total_pages
            )
            
            result = {
                "document_id": f"{company.replace(' ', '_').lower()}_{year}",
                "file_name": pdf_path.name,
                "company": company,
                "sector": sector,
                "year": year,
                "total_pages": total_pages,
                "total_chunks": len(chunks_with_metadata),
                "total_characters": sum(c["char_count"] for c in chunks_with_metadata),
                "source": "AMMC",
                "classification": "PUBLIC",  # Par défaut, sera configurable
                "allowed_roles": ["employee", "manager", "executive"],
                "chunks": chunks_with_metadata
            }
            
            logger.info(f"✅ {pdf_path.name}: {total_pages} pages, {len(chunks_with_metadata)} chunks créés")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur traitement {pdf_path.name}: {str(e)}")
            return None
    
    def _create_chunks_with_metadata(
        self,
        pages_content: List[Dict],
        company: str,
        sector: str,
        year: int,
        filename: str,
        total_pages: int
    ) -> List[Dict[str, Any]]:
        """
        Créer des chunks en conservant la structure et les métadonnées
        """
        chunks = []
        chunk_id = 0
        
        current_chunk = {
            "text": "",
            "page_start": None,
            "page_end": None,
            "char_count": 0,
            "word_count": 0
        }
        
        for page_data in pages_content:
            page_num = page_data["page"]
            page_text = page_data["text"]
            
            if not page_text.strip():
                continue
            
            # NE PAS supprimer les sauts de ligne avant de détecter les paragraphes
            # On garde la structure originale
            
            # Si la page est très grande, on la découpe en paragraphes
            if len(page_text) > self.chunk_size * 1.5:
                # Finaliser le chunk en cours
                if current_chunk["text"]:
                    current_chunk["page_end"] = page_num - 1
                    chunks.append(self._finalize_chunk(
                        current_chunk, chunk_id, company, sector, year, filename
                    ))
                    chunk_id += 1
                    current_chunk = {
                        "text": "",
                        "page_start": None,
                        "page_end": None,
                        "char_count": 0,
                        "word_count": 0
                    }
                
                # Découper la page en paragraphes
                paragraphs = self._split_into_paragraphs(page_text)
                
                temp_chunk = {
                    "text": "",
                    "page_start": page_num,
                    "page_end": page_num,
                    "char_count": 0,
                    "word_count": 0
                }
                
                for para in paragraphs:
                    if not para.strip():
                        continue
                    
                    # Si ajouter ce paragraphe dépasse la taille max
                    if temp_chunk["char_count"] + len(para) > self.chunk_size:
                        if temp_chunk["text"]:
                            temp_chunk["page_end"] = page_num
                            chunks.append(self._finalize_chunk(
                                temp_chunk, chunk_id, company, sector, year, filename
                            ))
                            chunk_id += 1
                            
                            # Nouveau chunk avec chevauchement
                            overlap_text = self._get_overlap(temp_chunk["text"], self.chunk_overlap)
                            temp_chunk = {
                                "text": overlap_text + "\n\n" if overlap_text else "",
                                "page_start": page_num,
                                "page_end": page_num,
                                "char_count": len(overlap_text) if overlap_text else 0,
                                "word_count": len(overlap_text.split()) if overlap_text else 0
                            }
                    
                    temp_chunk["text"] += para + "\n\n"
                    temp_chunk["char_count"] += len(para) + 2
                    temp_chunk["word_count"] += len(para.split()) + 2
                
                # Ajouter le dernier chunk de cette page
                if temp_chunk["text"]:
                    temp_chunk["page_end"] = page_num
                    chunks.append(self._finalize_chunk(
                        temp_chunk, chunk_id, company, sector, year, filename
                    ))
                    chunk_id += 1
                
                continue
            
            # Cas normal : ajouter la page au chunk courant
            if current_chunk["page_start"] is None:
                current_chunk["page_start"] = page_num
            
            # Si ajouter cette page dépasse la taille max
            if current_chunk["char_count"] + len(page_text) > self.chunk_size:
                # Finaliser le chunk courant
                current_chunk["page_end"] = page_num - 1
                if current_chunk["text"]:
                    chunks.append(self._finalize_chunk(
                        current_chunk, chunk_id, company, sector, year, filename
                    ))
                    chunk_id += 1
                
                # Nouveau chunk avec chevauchement
                overlap_text = self._get_overlap(current_chunk["text"], self.chunk_overlap)
                current_chunk = {
                    "text": overlap_text + "\n\n" if overlap_text else "",
                    "page_start": page_num,
                    "page_end": page_num,
                    "char_count": len(overlap_text) if overlap_text else 0,
                    "word_count": len(overlap_text.split()) if overlap_text else 0
                }
            
            # Ajouter le texte de la page (CONSERVER les sauts de ligne)
            current_chunk["text"] += page_text + "\n"
            current_chunk["char_count"] += len(page_text) + 1
            current_chunk["word_count"] += len(page_text.split()) + 1
            current_chunk["page_end"] = page_num
        
        # Ajouter le dernier chunk
        if current_chunk["text"] and current_chunk["char_count"] >= self.min_chunk_size:
            current_chunk["page_end"] = total_pages
            chunks.append(self._finalize_chunk(
                current_chunk, chunk_id, company, sector, year, filename
            ))
            chunk_id += 1
        
        return chunks
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """
        Diviser le texte en paragraphes en conservant la structure
        """
        # Garder les doubles sauts de ligne comme séparateurs de paragraphes
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _get_overlap(self, text: str, overlap_chars: int) -> str:
        """
        Extraire les derniers caractères pour le chevauchement
        """
        if len(text) <= overlap_chars:
            return text
        
        # Trouver un bon point de coupe (fin de phrase ou paragraphe)
        overlap_text = text[-overlap_chars:]
        
        # Essayer de couper à la fin d'une phrase
        sentence_ends = ['. ', '! ', '? ', '\n\n']
        for end in sentence_ends:
            last_end = overlap_text.rfind(end)
            if last_end > overlap_chars // 2:
                return overlap_text[:last_end + len(end)]
        
        return overlap_text
    
    def _finalize_chunk(
        self,
        chunk_data: Dict,
        chunk_id: int,
        company: str,
        sector: str,
        year: int,
        filename: str
    ) -> Dict[str, Any]:
        """
        Finaliser un chunk avec toutes ses métadonnées
        """
        text = chunk_data["text"].strip()
        
        # Nettoyer les espaces multiples mais GARDER les sauts de ligne
        text = re.sub(r'[ \t]+', ' ', text)  # Remplacer multiples espaces/tabs par un seul
        text = re.sub(r'\n{3,}', '\n\n', text)  # Limiter les sauts de ligne multiples
        
        # Générer un ID unique pour le chunk
        doc_id = f"{company.replace(' ', '_').lower()}_{year}"
        chunk_id_str = f"{chunk_id:04d}"
        
        return {
            "chunk_id": f"{doc_id}_{chunk_id_str}",
            "document_id": doc_id,
            "text": text,
            "company": company,
            "sector": sector,
            "year": year,
            "filename": filename,
            "page_start": chunk_data["page_start"],
            "page_end": chunk_data["page_end"],
            "page_count": chunk_data["page_end"] - chunk_data["page_start"] + 1,
            "char_count": len(text),
            "word_count": len(text.split()),
            "chunk_index": chunk_id,
            "source": "AMMC",
            "classification": "PUBLIC",
            "allowed_roles": ["employee", "manager", "executive"]
        }
    
    def ingest_all(self):
        """Ingérer tous les PDFs"""
        results = []
        
        pdf_files = list(self.base_path.glob("**/*.pdf"))
        
        logger.info(f"📊 {len(pdf_files)} PDFs trouvés")
        logger.info("="*50)
        
        for pdf_path in pdf_files:
            result = self.process_pdf(pdf_path)
            if result:
                # Sauvegarder les résultats
                output_file = pdf_path.parent / f"{pdf_path.stem}_chunks_v3.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                logger.info(f"💾 Chunks sauvegardés: {output_file.name}")
                results.append(result)
        
        # Résumé détaillé
        logger.info("\n" + "="*50)
        logger.info("📊 RÉSUMÉ DE L'INGESTION V3")
        logger.info("="*50)
        logger.info(f"Total PDFs: {len(pdf_files)}")
        logger.info(f"Traités avec succès: {len(results)}")
        
        if results:
            total_chunks = sum(r["total_chunks"] for r in results)
            total_pages = sum(r["total_pages"] for r in results)
            total_chars = sum(r["total_characters"] for r in results)
            
            logger.info(f"Total pages: {total_pages}")
            logger.info(f"✅ Total chunks créés: {total_chunks}")
            logger.info(f"📝 Total caractères: {total_chars:,}")
            
            # Statistiques par document
            logger.info("\n📄 Détail par document:")
            for r in results:
                chunks_info = r["chunks"]
                if chunks_info:
                    avg_words = sum(c["word_count"] for c in chunks_info) / len(chunks_info)
                    avg_pages = sum(c["page_count"] for c in chunks_info) / len(chunks_info)
                    logger.info(f"   - {r['company']} ({r['year']}): {r['total_chunks']} chunks, "
                              f"moy. {avg_words:.0f} mots, {avg_pages:.1f} pages/chunk")
            
            # Sauvegarder le résumé global
            summary = {
                "ingestion_date": datetime.utcnow().isoformat(),
                "version": "3.0",
                "total_documents": len(results),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "total_characters": total_chars,
                "documents": [
                    {
                        "document_id": r["document_id"],
                        "company": r["company"],
                        "sector": r["sector"],
                        "year": r["year"],
                        "total_chunks": r["total_chunks"],
                        "total_pages": r["total_pages"]
                    }
                    for r in results
                ]
            }
            
            with open(self.base_path / "ingestion_summary_v3.json", 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            logger.info(f"\n💾 Résumé sauvegardé: ingestion_summary_v3.json")
        
        return results

if __name__ == "__main__":
    print("🚀 INGESTION DES RAPPORTS AMMC - V3")
    print("="*50)
    print("✅ Conservation de la structure (paragraphes, titres)")
    print("✅ Métadonnées complètes par chunk")
    print("✅ Pages tracées précisément")
    print("✅ Préparation pour la sécurité (classification, rôles)")
    print("="*50)
    
    ingestor = DocumentIngestorV3()
    results = ingestor.ingest_all()
    
    print("\n✅ Ingestion V3 terminée !")
    print(f"📊 {len(results)} documents traités")
    
    if results:
        total_chunks = sum(r["total_chunks"] for r in results)
        print(f"📦 Total chunks sauvegardés: {total_chunks}")
        
        # Afficher un exemple de chunk
        if results and results[0]["chunks"]:
            example = results[0]["chunks"][0]
            print("\n📄 Exemple de chunk avec métadonnées:")
            print(f"   chunk_id: {example['chunk_id']}")
            print(f"   company: {example['company']}")
            print(f"   pages: {example['page_start']} - {example['page_end']}")
            print(f"   mots: {example['word_count']}")
            print(f"   texte: {example['text'][:150]}...")
