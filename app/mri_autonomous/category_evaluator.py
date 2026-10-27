import re
from typing import Dict, Any, Optional

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = str(s).lower()
    repl = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n'}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s.strip()

GARMENT_FAMILIES = {
    'blazer': {
        'family': 'blazer',
        'keywords': ['blazer', 'sastrero'],
        'contradictions': ['sweater', 'sweaters', 'chaleco', 'cardigan', 'chompa', 'pantalon', 'jeans', 'vestido', 'falda', 'polera']
    },
    'vestido': {
        'family': 'vestido',
        'keywords': ['vestido', 'enterito', 'jumpsuit'],
        'contradictions': ['pantalon', 'jeans', 'blazer', 'chaqueta', 'sweater', 'sweaters', 'cardigan', 'chaleco']
    },
    'pantalon': {
        'family': 'pantalon',
        'keywords': ['pantalon', 'pantalones', 'jeans', 'short', 'shorts', 'bermuda'],
        'contradictions': ['blazer', 'chaqueta', 'vestido', 'sweater', 'sweaters', 'blusa', 'cardigan']
    },
    'chaqueta': {
        'family': 'chaqueta',
        'keywords': ['chaqueta', 'abrigo', 'parka', 'trench', 'biker', 'cazadora'],
        'contradictions': ['pantalon', 'jeans', 'vestido', 'falda', 'polera']
    },
    'sweater': {
        'family': 'sweater',
        'keywords': ['sweater', 'sweaters', 'chaleco', 'cardigan', 'chompa', 'poleron'],
        'contradictions': ['blazer', 'vestido', 'pantalon', 'jeans', 'falda']
    },
    'blusa': {
        'family': 'blusa',
        'keywords': ['blusa', 'polera', 'top', 'camisa', 'remera'],
        'contradictions': ['pantalon', 'jeans', 'falda', 'vestido']
    },
    'falda': {
        'family': 'falda',
        'keywords': ['falda', 'pollera', 'skirt'],
        'contradictions': ['pantalon', 'jeans', 'blazer', 'sweater', 'sweaters', 'blusa']
    }
}

def evaluate_commercial_category(
    product_title: str,
    expected_category: str,
    observed_category: str,
    public_attributes: Optional[Dict[str, str]] = None,
    marketplace: Optional[str] = None,
    identity_status: Optional[str] = None,
    brand_corridor: Optional[str] = None
) -> Dict[str, Any]:
    title_norm = normalize_text(product_title)
    exp_norm = normalize_text(expected_category)
    obs_norm = normalize_text(observed_category)
    # Parent paths can contain contradictory words ("Jeans y Pantalones" for a
    # Pantalones product). Classify against the LEAF, not the whole breadcrumb.
    _obs_parts = [x.strip() for x in re.split(r"[→>]", str(observed_category)) if x.strip()]
    obs_leaf_norm = normalize_text(_obs_parts[-1]) if _obs_parts else obs_norm
    pub_attrs = public_attributes or {}

    # Gating 0: the expected category must be independent evidence. Never infer
    # it from the observed category and use equality as proof.
    if exp_norm in ("", "no verificado", "no_verificado", "sin referencia",
                    "sin_referencia", "none", "category unknown"):
        return {
            'decision': 'NO_VERIFICADO',
            'reason': 'Sin categoría esperada independiente: no se emite dictamen comercial.',
            'severity': 'INFO',
            'expected_category_status': 'SIN_REFERENCIA'
        }

    # Gating 1: Identidad no verificada
    # Si falta identidad unívoca con el catálogo maestro, no producir dictamen comercial definitivo
    if identity_status in ("IDENTIDAD_NO_VERIFICADA", "IDENTITY_NOT_LINKED"):
        return {
            'decision': 'REVIEW_REQUIRED',
            'reason': 'Identidad no verificada: no se puede emitir dictamen comercial sin correspondencia unívoca en catálogo maestro.',
            'severity': 'WARNING',
            'identity_status': 'IDENTIDAD_NO_VERIFICADA'
        }

    # Gating 2: Corredor de marca / Tienda de marca (Brand Store / Brand Hub)
    # Si la categoría observada es exclusivamente un corredor de marca y NO se observó categoría departamental
    is_brand_hub = any(m in obs_norm for m in ['marcas casuales', 'tienda_de_marca', 'tienda oficial', 'tienda/nicopoly', 'brand store', 'brand hub'])
    if is_brand_hub and not brand_corridor:
        return {
            'decision': 'REVIEW_REQUIRED',
            'reason': f'Ruta pública de corredor comercial ({observed_category}): corresponde a TIENDA_DE_MARCA y no acredita categoría departamental de prenda.',
            'severity': 'INFO',
            'corredor_tipo': 'TIENDA_DE_MARCA',
            'brand_corridor': observed_category
        }

    # Check ExperienceStore for prior validated learning / mapping
    try:
        from app.mri_autonomous.experience_store import ExperienceStore
        exp_store = ExperienceStore()
        # Look for category mapping rule learned and validated
        rule_val = f"{expected_category} -> {observed_category}"
        exp_item = exp_store.get_experience_item(marketplace or "GLOBAL", "Nicopoly", "CATEGORY_MAPPING", rule_val)
        if exp_item and exp_item.get("status") in ("VALIDATED", "LAST_GOOD"):
            # Register hit
            exp_store.record_experience(
                marketplace=marketplace or "GLOBAL",
                brand="Nicopoly",
                knowledge_type="CATEGORY_MAPPING",
                value=rule_val,
                status=exp_item.get("status"),
                is_success=True,
                evidence_reference="Reutilización automática de regla aprendida y validada"
            )
            return {
                'decision': 'CORRECT',
                'reason': f'Categoría validada mediante aprendizaje aplicado previo ({rule_val})',
                'severity': 'SUCCESS',
                'learning_applied': True
            }
    except Exception:
        pass

    # 1. Sin categoría pública válida
    if not observed_category or observed_category.strip() in (
        'NO_VERIFICADO', 'CATEGORY_UNKNOWN', 'NONE', 'Home', 'Brand Hub', ''
    ):
        return {
            'decision': 'NOT_VERIFIED',
            'reason': f'No se observó categoría pública específica en el canal comercial (dato: "{observed_category}")',
            'severity': 'INFO'
        }

    # 2. Detectar familia de prenda esperada
    expected_family = None
    for fam, info in GARMENT_FAMILIES.items():
        if any(kw in exp_norm for kw in info['keywords']) or any(kw in title_norm for kw in info['keywords']):
            expected_family = fam
            break

    # 3. Detectar contradicción material en atributos públicos explícitos
    for attr_k, attr_v in pub_attrs.items():
        v_norm = normalize_text(attr_v)
        if expected_family and expected_family in GARMENT_FAMILIES:
            contradictions = GARMENT_FAMILIES[expected_family]['contradictions']
            for c in contradictions:
                # Coincidencia exacta o palabra completa
                pattern = r'\b' + re.escape(c) + r'\b'
                if re.search(pattern, v_norm):
                    return {
                        'decision': 'INCORRECT',
                        'reason': f'Contradicción material: atributo público {attr_k}="{attr_v}" contradice tipo de prenda esperado "{expected_family.upper()}"',
                        'severity': 'ERROR'
                    }

    # 4. Detectar contradicción material en categoría observada
    if expected_family and expected_family in GARMENT_FAMILIES:
        contradictions = GARMENT_FAMILIES[expected_family]['contradictions']
        for c in contradictions:
            pattern = r'\b' + re.escape(c) + r'\b'
            if re.search(pattern, obs_leaf_norm):
                return {
                    'decision': 'INCORRECT',
                    'reason': f'Contradicción material: categoría pública "{observed_category}" contradice prenda esperada "{expected_family.upper()}"',
                    'severity': 'ERROR'
                }

    # 5. Categoría observada alineada con la familia
    if expected_family and expected_family in GARMENT_FAMILIES:
        family_keywords = GARMENT_FAMILIES[expected_family]['keywords']
        # Spanish plural tolerance: blazer -> blazers, blusa -> blusas, falda -> faldas
        if any(re.search(r'\b' + re.escape(kw) + r'(?:s|es)?\b', obs_leaf_norm)
               for kw in family_keywords):
            # Verificar si la hoja de la taxonomía del maestro coincide de forma exacta.
            # Master categories use "Ropa - Ropa Mujer - Chaquetas - Blazers"; the
            # observed Ripley leaf is "Chaquetas y blazers". Compare the leaf token
            # (singular/plural tolerant) before falling back to REVIEW.
            _parts = [p for p in re.split(r"\s*-\s*", exp_norm) if p]
            exp_leaf = (_parts[-1] if _parts else exp_norm).strip()
            # The master path can be more specific than the Ripley leaf
            # ("Blusas - Blusas Manga Larga" vs "Blusas y poleras"). Compare
            # commercial category segments, not only the final subtype.
            for _part in _parts:
                _part_norm = normalize_text(_part).strip()
                if _part_norm in ("ropa", "ropa mujer", "mujer", ""):
                    continue
                _variants = {_part_norm, _part_norm.rstrip("s"), _part_norm + "s"}
                if any(v and re.search(r'\b' + re.escape(v) + r'\b', obs_leaf_norm)
                       for v in _variants):
                    return {
                        'decision': 'CORRECT',
                        'reason': f'Categoría pública "{observed_category}" contiene la categoría comercial "{_part}"',
                        'severity': 'SUCCESS'
                    }
            leaf_words = [w for w in exp_leaf.split() if len(w) > 3]
            leaf_full_match = all(re.search(r'\b' + re.escape(w) + r'\b', obs_leaf_norm) for w in leaf_words)
            if leaf_full_match and len(leaf_words) >= 2:
                return {
                    'decision': 'CORRECT',
                    'reason': f'Categoría pública "{observed_category}" coincide unívocamente con nivel hoja esperado ("{exp_leaf}")',
                    'severity': 'SUCCESS'
                }
            else:
                return {
                    'decision': 'REVIEW_REQUIRED',
                    'reason': f'Categoría pública "{observed_category}" es compatible a nivel general pero nivel hoja ("{exp_leaf}") requiere validación',
                    'severity': 'WARNING'
                }

    # 6. Caso default: requiere revisión
    return {
        'decision': 'REVIEW_REQUIRED',
        'reason': f'Categoría pública "{observed_category}" observada pero requiere validación de equivalencia frente a "{expected_category}"',
        'severity': 'WARNING'
    }

