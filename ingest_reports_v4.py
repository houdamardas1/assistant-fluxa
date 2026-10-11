#!/usr/bin/env python3
"""
Script d'ingestion des rapports AMMC - V4
- Correction d'encodage (UTF-8 pur)
- Chunking sémantique (titres, sections, paragraphes)
- Conservation du contexte (pages, sections)
- Métadonnées enrichies
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import pdfplumber
import re
import unicodedata

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentIngestorV4:
    """
    Ingestion des documents AMMC - Version 4
    Avec encodage propre et chunking sémantique
    """
    
    def __init__(self):
        self.base_path = Path("data/raw")
        self.chunk_size = 1200
        self.chunk_overlap = 200
        self.min_chunk_size = 150
    
    def clean_text(self, text: str) -> str:
        """
        Nettoyer le texte et corriger l'encodage
        """
        if not text:
            return ""
        
        # 1. Normaliser les caractères Unicode
        text = unicodedata.normalize('NFC', text)
        
        # 2. Correction des caractères courants mal encodés
        replacements = {
            'Ã©': 'é',
            'Ã¨': 'è',
            'Ãª': 'ê',
            'Ã«': 'ë',
            'Ã¤': 'ä',
            'Ã®': 'î',
            'Ã¯': 'ï',
            'Ã´': 'ô',
            'Ã¶': 'ö',
            'Ã¹': 'ù',
            'Ã»': 'û',
            'Ã§': 'ç',
            'Ã ': 'à',
            'â‚¬': '€',
            'â€˜': "'",
            'â€™': "'",
            'â€œ': '"',
            'â€': '"',
            'â€¦': '...',
            'Â ': ' ',
            'Ãƒ': 'À',
            'Ã‰': 'É',
            'Ãˆ': 'È',
            'ÃŠ': 'Ê',
            'Ã‹': 'Ë',
            'ÃŽ': 'Î',
            'Ã': 'Ï',
            'Ã”': 'Ô',
            'Ã–': 'Ö',
            'Ã™': 'Ù',
            'Ã›': 'Û',
            'Ã‡': 'Ç',
        }
        
        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)
        
        # 3. Nettoyer les caractères de contrôle
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        
        return text
    
    def detect_sections(self, text: str) -> List[Dict[str, Any]]:
        """
        Détecter les sections et titres dans le texte
        """
        sections = []
        lines = text.split('\n')
        
        current_section = {
            "title": "Début du document",
            "level": 0,
            "content": [],
            "start_line": 0
        }
        
        # Patterns de titres courants
        title_patterns = [
            (r'^[IVXLCDM]+\.?\s+', 1),
            (r'^[0-9]+\.?\s+', 1),
            (r'^[A-Z][A-Z\s]{2,}$', 1),
            (r'^[A-Z][a-z]+\s+[A-Z][a-z]+', 2),
            (r'^[A-Z]{2,}\s+[A-Z]{2,}', 2),
        ]
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            is_title = False
            title_level = 0
            
            for pattern, level in title_patterns:
                if re.match(pattern, line):
                    is_title = True
                    title_level = level
                    break
            
            if is_title:
                if current_section["content"]:
                    sections.append(current_section)
                
                current_section = {
                    "title": line,
                    "level": title_level,
                    "content": [],
                    "start_line": i
                }
            else:
                current_section["content"].append(line)
        
        if current_section["content"]:
            sections.append(current_section)
        
        return sections
    
    def process_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extraire le texte d'un PDF et créer des chunks avec métadonnées
        """
        try:
            logger.info(f"📄 Traitement de: {pdf_path.name}")
            
            # Extraire les métadonnées du chemin
            company = pdf_path.parent.name.replace("_", " ")
            sector = pdf_path.parent.parent.name.replace("_", " ")
            
            year_match = re.search(r'(\d{4})', pdf_path.name)
            year = int(year_match.group(1)) if year_match else None
            
            # Extraction page par page
            pages_content = []
            total_pages = 0
            full_text = ""
            
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        page_text = self.clean_text(page_text)
                        pages_content.append({
                            "page": page_num,
                            "text": page_text,
                            "char_count": len(page_text)
                        })
                        full_text += page_text + "\n"
                    if page_num % 10 == 0:
                        logger.info(f"  Page {page_num}/{total_pages} traitée")
            
            # Détecter les sections
            sections = self.detect_sections(full_text)
            
            # Créer des chunks sémantiques
            chunks = self._create_semantic_chunks(
                pages_content=pages_content,
                sections=sections,
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
                "total_chunks": len(chunks),
                "total_characters": sum(c["char_count"] for c in chunks),
                "source": "AMMC",
                "classification": "PUBLIC",
                "allowed_roles": ["employee", "manager", "executive"],
                "chunks": chunks
            }
            
            logger.info(f"✅ {pdf_path.name}: {total_pages} pages, {len(chunks)} chunks sémantiques créés")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur traitement {pdf_path.name}: {str(e)}")
            return None
    
    def _create_semantic_chunks(
        self,
        pages_content: List[Dict],
        sections: List[Dict],
        company: str,
        sector: str,
        year: int,
        filename: str,
        total_pages: int
    ) -> List[Dict[str, Any]]:
        """
        Créer des chunks sémantiques basés sur les sections
        """
        chunks = []
        chunk_id = 0
        
        for section in sections:
            section_title = section["title"]
            section_content = "\n".join(section["content"])
            
            if len(section_content) < self.chunk_size:
                chunk = self._create_chunk(
                    text=f"{section_title}\n\n{section_content}",
                    chunk_id=chunk_id,
                    company=company,
                    sector=sector,
                    year=year,
                    filename=filename,
                    pages_content=pages_content,
                    section_title=section_title
                )
                if chunk:
                    chunks.append(chunk)
                    chunk_id += 1
            else:
                sub_chunks = self._split_section(
                    section_title=section_title,
                    section_content=section_content,
                    chunk_id=chunk_id,
                    company=company,
                    sector=sector,
                    year=year,
                    filename=filename,
                    pages_content=pages_content
                )
                chunks.extend(sub_chunks)
                chunk_id += len(sub_chunks)
        
        return chunks
    
    def _split_section(
        self,
        section_title: str,
        section_content: str,
        chunk_id: int,
        company: str,
        sector: str,
        year: int,
        filename: str,
        pages_content: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Découper une section en sous-chunks cohérents
        """
        chunks = []
        current_chunk_id = chunk_id
        
        paragraphs = re.split(r'\n\s*\n', section_content)
        current_text = f"{section_title}\n\n"
        current_words = len(current_text.split())
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_words = len(para.split())
            
            if current_words + para_words > self.chunk_size and current_words > self.min_chunk_size:
                chunk = self._create_chunk(
                    text=current_text,
                    chunk_id=current_chunk_id,
                    company=company,
                    sector=sector,
                    year=year,
                    filename=filename,
                    pages_content=pages_content,
                    section_title=section_title
                )
                if chunk:
                    chunks.append(chunk)
                    current_chunk_id += 1
                    
                    overlap = self._get_overlap(current_text, self.chunk_overlap)
                    current_text = overlap + "\n\n" if overlap else ""
                    current_words = len(current_text.split())
            
            current_text += para + "\n\n"
            current_words += para_words + 2
        
        if current_text.strip():
            chunk = self._create_chunk(
                text=current_text,
                chunk_id=current_chunk_id,
                company=company,
                sector=sector,
                year=year,
                filename=filename,
                pages_content=pages_content,
                section_title=section_title
            )
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _create_chunk(
        self,
        text: str,
        chunk_id: int,
        company: str,
        sector: str,
        year: int,
        filename: str,
        pages_content: List[Dict],
        section_title: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        Créer un chunk avec toutes ses métadonnées
        """
        text = text.strip()
        if len(text) < self.min_chunk_size:
            return None
        
        text = self.clean_text(text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        pages = self._find_pages(text, pages_content)
        
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
            "section_title": section_title,
            "page_start": pages["start"],
            "page_end": pages["end"],
            "page_count": pages["end"] - pages["start"] + 1 if pages["start"] and pages["end"] else 1,
            "char_count": len(text),
            "word_count": len(text.split()),
            "chunk_index": chunk_id,
            "source": "AMMC",
            "classification": "PUBLIC",
            "allowed_roles": ["employee", "manager", "executive"],
            "has_tables": "TABLEAU" in text.upper() or "COMPTE" in text.upper()
        }
    
    def _find_pages(self, text: str, pages_content: List[Dict]) -> Dict[str, Optional[int]]:
        """
        Trouver les pages correspondant à un chunk
        """
        first_words = text[:200].strip()
        last_words = text[-200:].strip()
        
        start_page = None
        end_page = None
        
        for page_data in pages_content:
            page_text = page_data["text"]
            
            if start_page is None and first_words in page_text:
                start_page = page_data["page"]
            
            if last_words in page_text:
                end_page = page_data["page"]
        
        if start_page is None and end_page is not None:
            start_page = max(1, end_page - 2)
        elif end_page is None and start_page is not None:
            end_page = min(len(pages_content), start_page + 2)
        elif start_page is None and end_page is None:
            start_page = 1
            end_page = min(3, len(pages_content))
        
        return {"start": start_page, "end": end_page}
    
    def _get_overlap(self, text: str, overlap_chars: int) -> str:
        """
        Extraire les derniers caractères pour le chevauchement
        """
        if len(text) <= overlap_chars:
            return text
        
        overlap_text = text[-overlap_chars:]
        
        for separator in ['\n\n', '. ', '! ', '? ', '\n']:
            last_sep = overlap_text.rfind(separator)
            if last_sep > overlap_chars // 2:
                return overlap_text[:last_sep + len(separator)]
        
        return overlap_text
    
    def ingest_all(self):
        """Ingérer tous les PDFs"""
        results = []
        
        pdf_files = list(self.base_path.glob("**/*.pdf"))
        
        logger.info(f"📊 {len(pdf_files)} PDFs trouvés")
        logger.info("="*50)
        
        for pdf_path in pdf_files:
            result = self.process_pdf(pdf_path)
            if result:
                output_file = pdf_path.parent / f"{pdf_path.stem}_chunks_v4.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                logger.info(f"💾 Chunks sauvegardés: {output_file.name}")
                results.append(result)
        
        logger.info("\n" + "="*50)
        logger.info("📊 RÉSUMÉ DE L'INGESTION V4")
        logger.info("="*50)
        
        if results:
            total_chunks = sum(r["total_chunks"] for r in results)
            total_pages = sum(r["total_pages"] for r in results)
            
            logger.info(f"Total PDFs: {len(pdf_files)}")
            logger.info(f"Traités avec succès: {len(results)}")
            logger.info(f"Total pages: {total_pages}")
            logger.info(f"✅ Total chunks sémantiques: {total_chunks}")
            
            logger.info("\n📄 Détail par document:")
            for r in results:
                chunks = r["chunks"]
                if chunks:
                    avg_words = sum(c["word_count"] for c in chunks) / len(chunks)
                    logger.info(f"   - {r['company']} ({r['year']}): {r['total_chunks']} chunks, "
                              f"moy. {avg_words:.0f} mots/chunk")
            
            summary = {
                "ingestion_date": datetime.utcnow().isoformat(),
                "version": "4.0",
                "total_documents": len(results),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "documents": [
                    {
                        "document_id": r["document_id"],
                        "company": r["company"],
                        "year": r["year"],
                        "total_chunks": r["total_chunks"]
                    }
                    for r in results
                ]
            }
            
            with open(self.base_path / "ingestion_summary_v4.json", 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            logger.info(f"\n💾 Résumé sauvegardé: ingestion_summary_v4.json")
        
        return results

if __name__ == "__main__":
    print("🚀 INGESTION DES RAPPORTS AMMC - V4")
    print("="*50)
    print("✅ Correction d'encodage (UTF-8 pur)")
    print("✅ Chunking sémantique (titres, sections, paragraphes)")
    print("✅ Conservation du contexte")
    print("="*50)
    
    ingestor = DocumentIngestorV4()
    results = ingestor.ingest_all()
    
    print("\n✅ Ingestion V4 terminée !")
    print(f"📊 {len(results)} documents traités")
    
    if results:
        total_chunks = sum(r["total_chunks"] for r in results)
        print(f"📦 Total chunks sauvegardés: {total_chunks}")
        
        if results and results[0]["chunks"]:
            example = results[0]["chunks"][0]
            print("\n📄 Exemple de chunk V4:")
            print(f"   ID: {example['chunk_id']}")
            print(f"   Company: {example['company']}")
            print(f"   Section: {example['section_title']}")
            print(f"   Pages: {example['page_start']} → {example['page_end']}")
            print(f"   Mots: {example['word_count']}")
            print(f"   Texte: {example['text'][:150]}...")
