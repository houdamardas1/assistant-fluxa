#!/usr/bin/env python3
"""
Script de validation qualité pour l'ingestion V4
Vérifie la structure, l'encodage, les pages, les chunks et génère un rapport
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict, Counter
import re

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QualityChecker:
    """
    Vérificateur de qualité pour les chunks ingérés
    """
    
    def __init__(self):
        self.base_path = Path("data/raw")
        self.report = {}
    
    def check_all(self) -> Dict[str, Any]:
        """
        Vérifier tous les fichiers chunks V4
        """
        results = []
        chunks_files = list(self.base_path.glob("**/*_chunks_v4.json"))
        
        logger.info(f"📊 {len(chunks_files)} fichiers chunks V4 trouvés")
        logger.info("="*50)
        
        for file_path in chunks_files:
            logger.info(f"\n📄 Vérification: {file_path.name}")
            result = self.check_file(file_path)
            if result:
                results.append(result)
                self._print_summary(result)
        
        # Générer le rapport global
        report = {
            "check_date": datetime.utcnow().isoformat(),
            "total_documents": len(results),
            "documents": results
        }
        
        # Statistiques globales
        if results:
            total_chunks = sum(r["statistics"]["total_chunks"] for r in results)
            total_pages = sum(r["statistics"]["total_pages"] for r in results)
            
            report["global_statistics"] = {
                "total_documents": len(results),
                "total_pages": total_pages,
                "total_chunks": total_chunks,
                "avg_chunks_per_doc": total_chunks / len(results) if results else 0,
                "avg_pages_per_doc": total_pages / len(results) if results else 0,
                "chunks_per_page": total_chunks / total_pages if total_pages > 0 else 0
            }
            
            # Distribution des tailles de chunks
            all_chunk_sizes = []
            for r in results:
                all_chunk_sizes.extend(r["statistics"]["chunk_sizes"])
            
            if all_chunk_sizes:
                report["global_statistics"]["chunk_size_distribution"] = {
                    "min": min(all_chunk_sizes),
                    "max": max(all_chunk_sizes),
                    "avg": sum(all_chunk_sizes) / len(all_chunk_sizes),
                    "median": sorted(all_chunk_sizes)[len(all_chunk_sizes) // 2],
                    "total_chunks": len(all_chunk_sizes)
                }
        
        # Sauvegarder le rapport
        report_file = self.base_path / "quality_report_v4.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n💾 Rapport sauvegardé: {report_file.name}")
        
        return report
    
    def check_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Vérifier un fichier chunks V4
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            chunks = data.get("chunks", [])
            total_pages = data.get("total_pages", 0)
            company = data.get("company", "Unknown")
            year = data.get("year", 0)
            
            # 1. Vérifier la structure des métadonnées
            required_fields = [
                "chunk_id", "document_id", "text", "company", "sector",
                "year", "filename", "section_title", "page_start", "page_end",
                "char_count", "word_count", "source", "classification"
            ]
            
            missing_fields = []
            if chunks:
                for field in required_fields:
                    if field not in chunks[0]:
                        missing_fields.append(field)
            
            # 2. Analyser les chunks
            chunk_analysis = self._analyze_chunks(chunks, total_pages)
            
            # 3. Vérifier les pages
            page_coverage = self._check_page_coverage(chunks, total_pages)
            
            # 4. Vérifier l'encodage
            encoding_issues = self._check_encoding(chunks)
            
            # 5. Vérifier les doublons
            duplicates = self._check_duplicates(chunks)
            
            # 6. Vérifier les sections
            section_analysis = self._analyze_sections(chunks)
            
            result = {
                "file_name": file_path.name,
                "company": company,
                "year": year,
                "statistics": {
                    "total_chunks": len(chunks),
                    "total_pages": total_pages,
                    "chunk_sizes": chunk_analysis["word_counts"],
                    "avg_words": chunk_analysis["avg_words"],
                    "min_words": chunk_analysis["min_words"],
                    "max_words": chunk_analysis["max_words"],
                    "median_words": chunk_analysis["median_words"],
                    "empty_chunks": chunk_analysis["empty_chunks"],
                    "chunks_by_size": chunk_analysis["chunks_by_size"]
                },
                "page_coverage": page_coverage,
                "encoding_issues": encoding_issues,
                "duplicates": duplicates,
                "section_analysis": section_analysis,
                "missing_fields": missing_fields,
                "issues": []
            }
            
            # Compiler les problèmes
            if missing_fields:
                result["issues"].append(f"Champs manquants: {', '.join(missing_fields)}")
            
            if encoding_issues["total"] > 0:
                result["issues"].append(f"Problèmes d'encodage: {encoding_issues['total']}")
            
            if duplicates["total"] > 0:
                result["issues"].append(f"Chunks dupliqués: {duplicates['total']}")
            
            if page_coverage["missing_pages"]:
                result["issues"].append(f"Pages manquantes: {len(page_coverage['missing_pages'])} pages")
            
            if chunk_analysis["empty_chunks"] > 0:
                result["issues"].append(f"Chunks vides: {chunk_analysis['empty_chunks']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification {file_path.name}: {str(e)}")
            return None
    
    def _analyze_chunks(self, chunks: List[Dict], total_pages: int) -> Dict[str, Any]:
        """
        Analyser la taille et la distribution des chunks
        """
        word_counts = []
        empty_chunks = 0
        chunks_by_size = {
            "< 50 mots": 0,
            "50-150 mots": 0,
            "150-300 mots": 0,
            "300-500 mots": 0,
            "> 500 mots": 0
        }
        
        for chunk in chunks:
            text = chunk.get("text", "")
            word_count = len(text.split())
            
            if word_count == 0:
                empty_chunks += 1
            elif word_count < 50:
                chunks_by_size["< 50 mots"] += 1
            elif word_count < 150:
                chunks_by_size["50-150 mots"] += 1
            elif word_count < 300:
                chunks_by_size["150-300 mots"] += 1
            elif word_count < 500:
                chunks_by_size["300-500 mots"] += 1
            else:
                chunks_by_size["> 500 mots"] += 1
            
            word_counts.append(word_count)
        
        return {
            "word_counts": word_counts,
            "avg_words": sum(word_counts) / len(word_counts) if word_counts else 0,
            "min_words": min(word_counts) if word_counts else 0,
            "max_words": max(word_counts) if word_counts else 0,
            "median_words": sorted(word_counts)[len(word_counts) // 2] if word_counts else 0,
            "empty_chunks": empty_chunks,
            "chunks_by_size": chunks_by_size
        }
    
    def _check_page_coverage(self, chunks: List[Dict], total_pages: int) -> Dict[str, Any]:
        """
        Vérifier la couverture des pages
        """
        covered_pages = set()
        page_ranges = []
        
        for chunk in chunks:
            start = chunk.get("page_start")
            end = chunk.get("page_end")
            
            if start and end:
                for page in range(start, end + 1):
                    if 1 <= page <= total_pages:
                        covered_pages.add(page)
                page_ranges.append((start, end))
        
        # Pages manquantes
        all_pages = set(range(1, total_pages + 1))
        missing_pages = all_pages - covered_pages
        
        # Vérifier les plages de pages invalides
        invalid_ranges = []
        for start, end in page_ranges:
            if start < 1 or end > total_pages or start > end:
                invalid_ranges.append((start, end))
        
        return {
            "total_pages": total_pages,
            "covered_pages": len(covered_pages),
            "coverage_percentage": (len(covered_pages) / total_pages * 100) if total_pages > 0 else 0,
            "missing_pages": sorted(list(missing_pages))[:20],  # Limiter pour lisibilité
            "invalid_ranges": invalid_ranges[:10]  # Limiter pour lisibilité
        }
    
    def _check_encoding(self, chunks: List[Dict]) -> Dict[str, Any]:
        """
        Vérifier les problèmes d'encodage
        """
        issues = []
        suspicious_chars = set()
        
        # Caractères suspectés d'être mal encodés
        suspicious_patterns = [
            ('Ã©', 'é'),
            ('Ã¨', 'è'),
            ('Ãª', 'ê'),
            ('Ã«', 'ë'),
            ('Ã¤', 'ä'),
            ('Ã®', 'î'),
            ('Ã¯', 'ï'),
            ('Ã´', 'ô'),
            ('Ã¶', 'ö'),
            ('Ã¹', 'ù'),
            ('Ã»', 'û'),
            ('Ã§', 'ç'),
            ('Ã ', 'à'),
        ]
        
        for chunk in chunks:
            text = chunk.get("text", "")
            
            # Vérifier les caractères suspects
            for wrong, correct in suspicious_patterns:
                if wrong in text:
                    suspicious_chars.add(wrong)
        
        return {
            "total": len(suspicious_chars),
            "suspicious_chars": list(suspicious_chars)[:10]  # Limiter pour lisibilité
        }
    
    def _check_duplicates(self, chunks: List[Dict]) -> Dict[str, Any]:
        """
        Vérifier les chunks dupliqués
        """
        texts = []
        duplicates = []
        
        for i, chunk in enumerate(chunks):
            text = chunk.get("text", "").strip()
            if text:
                if text in texts:
                    duplicates.append({
                        "index": i,
                        "text_preview": text[:50] + "..."
                    })
                else:
                    texts.append(text)
        
        return {
            "total": len(duplicates),
            "duplicates": duplicates[:5]  # Limiter pour lisibilité
        }
    
    def _analyze_sections(self, chunks: List[Dict]) -> Dict[str, Any]:
        """
        Analyser les sections
        """
        sections = {}
        for chunk in chunks:
            section = chunk.get("section_title", "Unknown")
            if section not in sections:
                sections[section] = 0
            sections[section] += 1
        
        # Trier par nombre de chunks
        sorted_sections = sorted(sections.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "total_sections": len(sections),
            "top_sections": sorted_sections[:10],
            "sections_with_single_chunk": sum(1 for count in sections.values() if count == 1)
        }
    
    def _print_summary(self, result: Dict[str, Any]):
        """
        Afficher un résumé des résultats
        """
        stats = result["statistics"]
        page_cov = result["page_coverage"]
        
        print(f"\n   📊 Résumé pour {result['company']} ({result['year']}):")
        print(f"   📄 Pages: {stats['total_pages']} (couvertes: {page_cov['covered_pages']}/{stats['total_pages']} - {page_cov['coverage_percentage']:.1f}%)")
        print(f"   📦 Chunks: {stats['total_chunks']}")
        print(f"   📝 Moy. mots: {stats['avg_words']:.0f} (min: {stats['min_words']}, max: {stats['max_words']})")
        
        # Distribution
        print(f"\n   📊 Distribution des tailles:")
        for size_range, count in stats['chunks_by_size'].items():
            if count > 0:
                print(f"      {size_range}: {count}")
        
        # Problèmes
        if result["issues"]:
            print(f"\n   ⚠️  Problèmes détectés: {len(result['issues'])}")
            for issue in result["issues"]:
                print(f"      - {issue}")

if __name__ == "__main__":
    print("🔍 VALIDATION QUALITÉ - INGESTION V4")
    print("="*50)
    print("✅ Vérification de l'encodage")
    print("✅ Vérification des pages")
    print("✅ Vérification des chunks")
    print("✅ Vérification des sections")
    print("="*50)
    
    checker = QualityChecker()
    report = checker.check_all()
    
    print("\n✅ Validation terminée !")
    
    if report.get("global_statistics"):
        stats = report["global_statistics"]
        print(f"\n📊 RÉSULTATS GLOBAUX:")
        print(f"   Documents: {stats['total_documents']}")
        print(f"   Total pages: {stats['total_pages']}")
        print(f"   Total chunks: {stats['total_chunks']}")
        print(f"   Chunks/page: {stats['chunks_per_page']:.2f}")
        
        if stats.get("chunk_size_distribution"):
            dist = stats["chunk_size_distribution"]
            print(f"\n   📝 Distribution des chunks:")
            print(f"      Min mots: {dist['min']}")
            print(f"      Max mots: {dist['max']}")
            print(f"      Moy mots: {dist['avg']:.0f}")
            print(f"      Médian mots: {dist['median']}")
    
    # Vérifier le rapport généré
    report_file = Path("data/raw/quality_report_v4.json")
    if report_file.exists():
        size = report_file.stat().st_size / 1024
        print(f"\n💾 Rapport sauvegardé: {report_file.name} ({size:.1f} KB)")
