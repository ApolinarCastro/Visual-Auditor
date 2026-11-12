import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.mri_autonomous.storage_guard import StorageConfig
from app.mri_autonomous.autonomous_multimarketplace_runner import AutonomousMultiMarketplaceRunner
from app.mri_dashboard.mri_api import app
from starlette.testclient import TestClient
import pytest

@pytest.mark.asyncio
async def test_e2e_isolated_flow():
    await run_e2e_isolated()

async def run_e2e_isolated():
    temp_dir = tempfile.mkdtemp(prefix="mri_e2e_isolated_")
    test_db = os.path.join(temp_dir, "e2e_visibility.db")
    
    print("=" * 60)
    print("INICIANDO EJECUCIÓN E2E AISLADA - VISUAL AUDITOR")
    print(f"Directorio temporal: {temp_dir}")
    print(f"Base de datos aislada: {test_db}")
    print("=" * 60)
    
    StorageConfig.set_test_mode(True, temp_dir)
    test_db = str(StorageConfig.get_sqlite_path())
    
    try:
        # FASE 1: Adquisición, Selección de Estrategias y Persistencia SQLite
        print("\n[FASE 1] Instanciando AutonomousMultiMarketplaceRunner...")
        runner = AutonomousMultiMarketplaceRunner(db_path=test_db)
        
        print("[FASE 1] Ejecutando orden multi-marketplace autónoma...")
        report = await runner.execute_autonomous_order(run_id_prefix="run_e2e_isolated")
        
        print("\n--- REPORTE DE EJECUCIÓN MULTI-MARKETPLACE ---")
        print(f"Run ID: {report.run_id}")
        print(f"Target Brand: {report.target_brand}")
        print(f"Cross Marketplace Status: {report.summary.get('cross_marketplace_status')}")
        print(f"Total Publicaciones Persistidas: {report.summary.get('total_publications_persisted')}")
        
        for mkt, mkt_res in report.marketplaces.items():
            print(f"\nMarketplace: {mkt}")
            print(f"  Status: {mkt_res.status}")
            print(f"  Active Strategy: {mkt_res.active_strategy}")
            print(f"  Publications Acquired: {mkt_res.publications_count}")
            print(f"  Strategies Attempted: {[s.get('name') for s in mkt_res.strategies_attempted]}")
            if mkt_res.blocker_reason:
                print(f"  Blocker Reason: {mkt_res.blocker_reason}")
            if mkt_res.evidence:
                print(f"  Evidence Summary: {json.dumps(mkt_res.evidence, indent=4)}")

        # FASE 2: Conexión y Verificación de la API y Dashboard
        print("\n" + "=" * 60)
        print("[FASE 2] Verificando endpoints de la API y conexión con Dashboard...")
        client = TestClient(app)
        
        # 1. Dashboard UI HTML endpoint
        resp_ui = client.get("/")
        print(f"GET / -> Status Code: {resp_ui.status_code}")
        assert resp_ui.status_code == 200, f"Expected 200 for UI, got {resp_ui.status_code}"
        assert "MRI — Autonomous Marketplace Auditor" in resp_ui.text or "Visual Auditor" in resp_ui.text
        
        # 2. History endpoint
        resp_hist = client.get("/api/history")
        print(f"GET /api/history -> Status Code: {resp_hist.status_code}")
        assert resp_hist.status_code == 200
        hist_data = resp_hist.json()
        runs = hist_data.get("history", [])
        print(f"  Total corridas encontradas en historial: {len(runs)}")
        matching_runs = [r for r in runs if r.get("run_id") == report.run_id]
        assert len(matching_runs) == 1, f"Expected run {report.run_id} in history"
        print(f"  Corrida registrada en historial: {matching_runs[0]}")
        
        # 3. History run detail endpoint
        resp_detail = client.get(f"/api/history/{report.run_id}")
        print(f"GET /api/history/{report.run_id} -> Status Code: {resp_detail.status_code}")
        assert resp_detail.status_code == 200
        detail_data = resp_detail.json()
        print(f"  Publicaciones devueltas para la corrida: {detail_data.get('count')}")
        assert detail_data.get("count") == report.summary.get("total_publications_persisted")
        
        # 4. Latest summary endpoint
        resp_summary = client.get(f"/api/multimarketplace/summary?run_id={report.run_id}")
        print(f"GET /api/multimarketplace/summary?run_id={report.run_id} -> Status Code: {resp_summary.status_code}")
        assert resp_summary.status_code == 200
        summary_data = resp_summary.json()
        print(f"  Estado de resumen ejecutivo: {summary_data.get('status')}")
        print(f"  Marketplaces operativos: {summary_data.get('operational_marketplaces_count')}/4")
        for mkt_name, mkt_info in summary_data.get("marketplaces", {}).items():
            print(f"    - {mkt_name}: status={mkt_info.get('status')}, pubs={mkt_info.get('brand_publications')}")
            
        # 5. Categories endpoint
        resp_cats = client.get("/api/categories/Paris")
        print(f"GET /api/categories/Paris -> Status Code: {resp_cats.status_code}")
        assert resp_cats.status_code == 200
        
        print("\n" + "=" * 60)
        print("FLUJO E2E AISLADO VERIFICADO CON ÉXITO: 100% OPERATIVO")
        print("=" * 60)

    finally:
        StorageConfig.set_test_mode(False)
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(run_e2e_isolated())
