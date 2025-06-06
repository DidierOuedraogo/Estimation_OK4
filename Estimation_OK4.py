import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import zipfile
import math
import seaborn as sns
from io import BytesIO
import datetime
import tempfile
import os
import traceback
import warnings
warnings.filterwarnings('ignore')

# Configuration de la page avec design optimisé
st.set_page_config(
    page_title="MineEstim - Krigeage Ordinaire",
    page_icon="⛏️",
    layout="wide"
)

# Appliquer du CSS personnalisé pour améliorer le design
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 1rem;
        color: #1E3A8A;
    }
    .sub-header {
        font-size: 1.2rem;
        text-align: center;
        color: #4B5563;
        margin-bottom: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        white-space: pre-wrap;
        border-radius: 4px 4px 0px 0px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #E0E7FF;
    }
</style>
""", unsafe_allow_html=True)

# Titre principal centré
st.markdown('<h1 class="main-header">MineEstim - Estimation par krigeage ordinaire</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Solution professionnelle d\'estimation géostatistique pour l\'industrie minière</p>', unsafe_allow_html=True)

# Fonction pour capturer et afficher les erreurs
def show_detailed_error(error_title, exception):
    st.error(error_title)
    st.write("**Détails de l'erreur:**")
    st.code(traceback.format_exc())
    st.write("**Type d'erreur:** ", type(exception).__name__)
    st.write("**Message d'erreur:** ", str(exception))

# Fonction pour tenter le chargement d'un fichier CSV avec différents paramètres
def attempt_csv_loading(file, encodings=['utf-8', 'latin1', 'iso-8859-1', 'cp1252'], 
                        separators=[',', ';', '\t', '|'], 
                        decimal_points=['.', ',']):
    best_df = None
    best_params = None
    best_score = -1
    
    def evaluate_quality(df):
        if df is None or df.empty:
            return -1
        col_count = len(df.columns)
        non_na_percent = df.notna().mean().mean() * 100
        numeric_cols = sum(pd.api.types.is_numeric_dtype(df[col]) for col in df.columns)
        score = col_count * 10 + non_na_percent + numeric_cols * 5
        return score
    
    for encoding in encodings:
        for sep in separators:
            for dec in decimal_points:
                try:
                    file.seek(0)
                    df = pd.read_csv(
                        file, 
                        sep=sep, 
                        decimal=dec, 
                        encoding=encoding,
                        low_memory=False,
                        on_bad_lines='warn',
                        engine='python',
                        nrows=1000
                    )
                    score = evaluate_quality(df)
                    if score > best_score:
                        file.seek(0)
                        complete_df = pd.read_csv(
                            file, 
                            sep=sep, 
                            decimal=dec, 
                            encoding=encoding,
                            low_memory=False,
                            on_bad_lines='warn'
                        )
                        best_df = complete_df
                        best_params = {'encoding': encoding, 'separator': sep, 'decimal': dec}
                        best_score = score
                except Exception:
                    continue
    
    return best_df, best_params

# Fonction pour nettoyer et préparer les données
def clean_and_prepare_data(df, col_x, col_y, col_z, col_value, col_domain=None, domain_filter=None):
    initial_rows = len(df)
    stats = {
        'Étape': ['Données initiales'],
        'Nombre de lignes': [initial_rows],
        'Lignes retirées': [0],
        'Raison': ['']
    }
    
    # Conversion des colonnes clés en numérique
    for col in [col_x, col_y, col_z, col_value]:
        if col in df.columns:
            non_numeric_before = df[col].isna().sum()
            df[col] = pd.to_numeric(df[col], errors='coerce')
            non_numeric_after = df[col].isna().sum()
            rows_affected = non_numeric_after - non_numeric_before
            
            if rows_affected > 0:
                stats['Étape'].append(f'Conversion numérique {col}')
                stats['Nombre de lignes'].append(len(df))
                stats['Lignes retirées'].append(rows_affected)
                stats['Raison'].append(f'Valeurs non numériques dans {col}')
    
    # Filtrage des NA dans les colonnes essentielles
    before_na_filter = len(df)
    df = df.dropna(subset=[col_x, col_y, col_z, col_value])
    rows_affected = before_na_filter - len(df)
    
    if rows_affected > 0:
        stats['Étape'].append('Filtrage valeurs manquantes')
        stats['Nombre de lignes'].append(len(df))
        stats['Lignes retirées'].append(rows_affected)
        stats['Raison'].append('Valeurs manquantes dans X, Y, Z ou Teneur')
    
    # Filtrage par domaine si spécifié
    if col_domain and col_domain != '-- Aucun --' and domain_filter:
        domain_filter_type, domain_filter_value = domain_filter
        before_domain_filter = len(df)
        
        if domain_filter_type == "=":
            df = df[df[col_domain] == domain_filter_value]
        elif domain_filter_type == "!=":
            df = df[df[col_domain] != domain_filter_value]
        elif domain_filter_type == "IN":
            df = df[df[col_domain].isin(domain_filter_value)]
        elif domain_filter_type == "NOT IN":
            df = df[~df[col_domain].isin(domain_filter_value)]
        
        rows_affected = before_domain_filter - len(df)
        
        if rows_affected > 0:
            stats['Étape'].append(f'Filtrage domaine {domain_filter_type}')
            stats['Nombre de lignes'].append(len(df))
            stats['Lignes retirées'].append(rows_affected)
            stats['Raison'].append(f'Ne correspond pas au filtre {col_domain} {domain_filter_type} {domain_filter_value}')
    
    stats_df = pd.DataFrame(stats)
    return df, stats_df

# Fonction pour créer une représentation visuelle des étapes de nettoyage
def plot_data_cleaning_steps(stats_df):
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=stats_df['Étape'],
        y=stats_df['Nombre de lignes'],
        name='Lignes restantes',
        marker_color='rgb(55, 83, 109)'
    ))
    
    fig.add_trace(go.Bar(
        x=stats_df['Étape'],
        y=stats_df['Lignes retirées'],
        name='Lignes retirées',
        marker_color='rgb(219, 64, 82)',
        text=stats_df['Raison'],
        textposition='auto'
    ))
    
    fig.update_layout(
        title_text='Impact des étapes de nettoyage des données',
        xaxis_title='Étape de traitement',
        yaxis_title='Nombre de lignes',
        barmode='group',
        bargap=0.15,
        bargroupgap=0.1
    )
    
    return fig

# Fonction pour convertir un DataFrame en composites
def df_to_composites(df, col_x, col_y, col_z, col_value, col_domain=None, density_column=None):
    composites = []
    
    for idx, row in df.iterrows():
        composite = {
            'X': float(row[col_x]),
            'Y': float(row[col_y]),
            'Z': float(row[col_z]),
            'VALUE': float(row[col_value])
        }
        
        if col_domain and col_domain != '-- Aucun --' and col_domain in row:
            composite['DOMAIN'] = row[col_domain]
        
        if density_column and density_column in row and pd.notna(row[density_column]):
            try:
                density_val = float(row[density_column])
                if density_val > 0:
                    composite['DENSITY'] = density_val
            except (ValueError, TypeError):
                pass
        
        composites.append(composite)
    
    return composites

# Fonction calculate_stats pour renvoyer les statistiques des valeurs
def calculate_stats(values):
    if not values or len(values) == 0:
        return {
            'count': 0,
            'min': 0,
            'max': 0,
            'mean': 0,
            'median': 0,
            'stddev': 0,
            'variance': 0,
            'cv': 0
        }
    
    values = np.array(values)
    return {
        'count': len(values),
        'min': np.min(values),
        'max': np.max(values),
        'mean': np.mean(values),
        'median': np.median(values),
        'stddev': np.std(values),
        'variance': np.var(values),
        'cv': np.std(values) / np.mean(values) if np.mean(values) != 0 else 0
    }

# Fonction is_point_inside_box - pour vérifier si un point est dans une enveloppe
def is_point_inside_box(point, box_bounds):
    min_bounds = box_bounds['min']
    max_bounds = box_bounds['max']
    
    return (
        min_bounds['x'] <= point['x'] <= max_bounds['x'] and
        min_bounds['y'] <= point['y'] <= max_bounds['y'] and
        min_bounds['z'] <= point['z'] <= max_bounds['z']
    )

# Fonction pour le variogramme et le krigeage
def euclidean_distance(p1, p2, anisotropy=None):
    if anisotropy is None:
        anisotropy = {'x': 1, 'y': 1, 'z': 1}
    
    dx = (p2['x'] - p1['x']) / anisotropy['x']
    dy = (p2['y'] - p1['y']) / anisotropy['y']
    dz = (p2['z'] - p1['z']) / anisotropy['z']
    
    return math.sqrt(dx**2 + dy**2 + dz**2)

def spherical_variogram(h, c0, c, a):
    if h == 0:
        return 0
    elif h >= a:
        return c0 + c
    else:
        return c0 + c * (1.5 * (h/a) - 0.5 * (h/a)**3)

def exponential_variogram(h, c0, c, a):
    if h == 0:
        return 0
    else:
        return c0 + c * (1 - math.exp(-3 * h / a))

def gaussian_variogram(h, c0, c, a):
    if h == 0:
        return 0
    else:
        return c0 + c * (1 - math.exp(-3 * h**2 / a**2))

def ordinary_kriging(point, samples, variogram_model, anisotropy=None):
    n = len(samples)
    if n == 0:
        return 0, 1.0  # Valeur par défaut, variance maximale
    
    # Si un échantillon est exactement au point à estimer, retourner sa valeur
    for sample in samples:
        if sample['x'] == point['x'] and sample['y'] == point['y'] and sample['z'] == point['z']:
            return sample['value'], 0.0  # Variance nulle pour un point exact
    
    # Matrice des covariances entre échantillons
    K = np.zeros((n+1, n+1))
    
    # Remplir la matrice K
    for i in range(n):
        for j in range(n):
            # Calculer la distance entre les échantillons i et j
            h = euclidean_distance({'x': samples[i]['x'], 'y': samples[i]['y'], 'z': samples[i]['z']}, 
                                   {'x': samples[j]['x'], 'y': samples[j]['y'], 'z': samples[j]['z']}, 
                                   anisotropy)
            
            # Calculer la valeur du variogramme pour cette distance
            if variogram_model['type'] == 'spherical':
                gamma = spherical_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
            elif variogram_model['type'] == 'exponential':
                gamma = exponential_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
            elif variogram_model['type'] == 'gaussian':
                gamma = gaussian_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
            
            # La covariance est le palier total moins le variogramme
            K[i, j] = variogram_model['total_sill'] - gamma
    
    # Ajouter les contraintes de la somme des poids = 1 (krigeage ordinaire)
    for i in range(n):
        K[i, n] = 1.0
        K[n, i] = 1.0
    K[n, n] = 0.0
    
    # Vecteur des covariances entre les échantillons et le point à estimer
    k = np.zeros(n+1)
    
    for i in range(n):
        # Calculer la distance entre l'échantillon i et le point à estimer
        h = euclidean_distance({'x': samples[i]['x'], 'y': samples[i]['y'], 'z': samples[i]['z']}, 
                               point, anisotropy)
        
        # Calculer la valeur du variogramme pour cette distance
        if variogram_model['type'] == 'spherical':
            gamma = spherical_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
        elif variogram_model['type'] == 'exponential':
            gamma = exponential_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
        elif variogram_model['type'] == 'gaussian':
            gamma = gaussian_variogram(h, variogram_model['nugget'], variogram_model['sill'], variogram_model['range'])
        
        # La covariance est le palier total moins le variogramme
        k[i] = variogram_model['total_sill'] - gamma
    
    # La dernière composante est 1 pour satisfaire la contrainte du krigeage ordinaire
    k[n] = 1.0
    
    # Résoudre le système pour trouver les poids
    try:
        weights = np.linalg.solve(K, k)
    except np.linalg.LinAlgError:
        # En cas de matrice singulière, ajouter un petit epsilon à la diagonale
        for i in range(n):
            K[i, i] += 1e-6
        try:
            weights = np.linalg.solve(K, k)
        except np.linalg.LinAlgError:
            # Si toujours singulière, utiliser une pseudo-inverse
            weights = np.linalg.lstsq(K, k, rcond=None)[0]
    
    # Extraire les poids du krigeage (sans le multiplicateur de Lagrange)
    lambda_weights = weights[:n]
    
    # Calculer l'estimation par krigeage
    estimate = sum(lambda_weights[i] * samples[i]['value'] for i in range(n))
    
    # Calculer la variance d'estimation (variance du krigeage)
    kriging_variance = variogram_model['total_sill'] - np.dot(lambda_weights, k[:n]) - weights[n]
    
    return estimate, kriging_variance

def create_block_model(composites, block_sizes, envelope_bounds=None, use_envelope=True):
    # Vérifier si les composites existent
    if not composites or len(composites) == 0:
        st.error("Aucun échantillon valide pour créer le modèle de blocs.")
        return [], {'min': {'x': 0, 'y': 0, 'z': 0}, 'max': {'x': 0, 'y': 0, 'z': 0}}
    
    # Déterminer les limites du modèle
    if use_envelope and envelope_bounds:
        min_bounds = envelope_bounds['min']
        max_bounds = envelope_bounds['max']
    else:
        x_values = [comp['X'] for comp in composites if 'X' in comp]
        y_values = [comp['Y'] for comp in composites if 'Y' in comp]
        z_values = [comp['Z'] for comp in composites if 'Z' in comp]
        
        if not x_values or not y_values or not z_values:
            st.error("Données insuffisantes pour déterminer les limites du modèle.")
            return [], {'min': {'x': 0, 'y': 0, 'z': 0}, 'max': {'x': 0, 'y': 0, 'z': 0}}
        
        min_bounds = {
            'x': math.floor(min(x_values) / block_sizes['x']) * block_sizes['x'],
            'y': math.floor(min(y_values) / block_sizes['y']) * block_sizes['y'],
            'z': math.floor(min(z_values) / block_sizes['z']) * block_sizes['z']
        }
        
        max_bounds = {
            'x': math.ceil(max(x_values) / block_sizes['x']) * block_sizes['x'],
            'y': math.ceil(max(y_values) / block_sizes['y']) * block_sizes['y'],
            'z': math.ceil(max(z_values) / block_sizes['z']) * block_sizes['z']
        }
    
    # Créer les blocs
    blocks = []
    
    x_range = np.arange(min_bounds['x'] + block_sizes['x']/2, max_bounds['x'] + block_sizes['x']/2, block_sizes['x'])
    y_range = np.arange(min_bounds['y'] + block_sizes['y']/2, max_bounds['y'] + block_sizes['y']/2, block_sizes['y'])
    z_range = np.arange(min_bounds['z'] + block_sizes['z']/2, max_bounds['z'] + block_sizes['z']/2, block_sizes['z'])
    
    with st.spinner('Création du modèle de blocs...'):
        progress_bar = st.progress(0)
        total_blocks = len(x_range) * len(y_range) * len(z_range)
        block_count = 0
        
        for x in x_range:
            for y in y_range:
                for z in z_range:
                    block = {
                        'x': x,
                        'y': y,
                        'z': z,
                        'size_x': block_sizes['x'],
                        'size_y': block_sizes['y'],
                        'size_z': block_sizes['z']
                    }
                    
                    # Vérifier si le bloc est dans l'enveloppe
                    if not use_envelope or is_point_inside_box(block, {'min': min_bounds, 'max': max_bounds}):
                        blocks.append(block)
                    
                    block_count += 1
                    if block_count % 100 == 0 or block_count == total_blocks:
                        progress_bar.progress(min(block_count / total_blocks, 1.0))
        
        progress_bar.progress(1.0)
    
    return blocks, {'min': min_bounds, 'max': max_bounds}

def estimate_block_model_kriging(empty_blocks, composites, kriging_params, search_params, variogram_model, density_method="constant", density_value=2.7):
    estimated_blocks = []
    
    # Vérifier si les entrées sont valides
    if not empty_blocks or len(empty_blocks) == 0:
        st.error("Aucun bloc à estimer.")
        return []
    
    if not composites or len(composites) == 0:
        st.error("Aucun échantillon disponible pour l'estimation.")
        return []
    
    # S'assurer que le modèle de variogramme a la bonne structure
    if not variogram_model:
        st.error("Aucun modèle de variogramme spécifié.")
        return []
    
    if 'total_sill' not in variogram_model:
        variogram_model['total_sill'] = variogram_model['nugget'] + variogram_model['sill']
    
    with st.spinner('Estimation par krigeage ordinaire...'):
        progress_bar = st.progress(0)
        total_blocks = len(empty_blocks)
        
        for idx, block in enumerate(empty_blocks):
            progress = idx / total_blocks
            if idx % 10 == 0 or idx == total_blocks - 1:  # Mettre à jour moins fréquemment pour plus de performance
                progress_bar.progress(progress)
            
            # Chercher les échantillons pour le krigeage
            samples = []
            density_samples = []
            
            for composite in composites:
                if 'X' not in composite or 'Y' not in composite or 'Z' not in composite or 'VALUE' not in composite:
                    continue
                
                # Appliquer l'anisotropie
                dx = (composite['X'] - block['x']) / kriging_params['anisotropy']['x']
                dy = (composite['Y'] - block['y']) / kriging_params['anisotropy']['y']
                dz = (composite['Z'] - block['z']) / kriging_params['anisotropy']['z']
                
                distance = math.sqrt(dx**2 + dy**2 + dz**2)
                
                if distance <= max(search_params['x'], search_params['y'], search_params['z']):
                    samples.append({
                        'x': composite['X'],
                        'y': composite['Y'],
                        'z': composite['Z'],
                        'value': composite['VALUE'],
                        'distance': distance
                    })
                    
                    # Si la densité est variable, ajouter les échantillons de densité
                    if density_method == "variable" and 'DENSITY' in composite:
                        density_samples.append({
                            'x': composite['X'],
                            'y': composite['Y'],
                            'z': composite['Z'],
                            'value': composite['DENSITY'],
                            'distance': distance
                        })
            
            samples.sort(key=lambda x: x['distance'])
            
            if len(samples) >= search_params['min_samples']:
                used_samples = samples[:min(len(samples), search_params['max_samples'])]
                
                # Estimation par krigeage
                estimate, variance = ordinary_kriging(
                    block, 
                    used_samples, 
                    variogram_model,
                    kriging_params['anisotropy']
                )
                
                estimated_block = block.copy()
                estimated_block['value'] = estimate
                estimated_block['estimation_variance'] = variance
                
                # Estimer la densité si nécessaire
                if density_method == "variable" and density_samples:
                    density_samples.sort(key=lambda x: x['distance'])
                    used_density_samples = density_samples[:min(len(density_samples), search_params['max_samples'])]
                    
                    density_estimate, _ = ordinary_kriging(
                        block, 
                        used_density_samples, 
                        variogram_model,
                        kriging_params['anisotropy']
                    )
                    
                    estimated_block['density'] = density_estimate
                else:
                    estimated_block['density'] = density_value
                
                estimated_blocks.append(estimated_block)
        
        progress_bar.progress(1.0)
    
    return estimated_blocks

def calculate_tonnage_grade(blocks, density_method="constant", density_value=2.7, method="above", cutoff_value=None, cutoff_min=None, cutoff_max=None):
    if not blocks:
        return {
            'cutoffs': [],
            'tonnages': [],
            'grades': [],
            'metals': []
        }, {
            'method': method,
            'min_grade': 0,
            'max_grade': 0
        }
    
    # Extraire les valeurs
    values = [block.get('value', 0) for block in blocks]
    
    if not values:
        return {
            'cutoffs': [],
            'tonnages': [],
            'grades': [],
            'metals': []
        }, {
            'method': method,
            'min_grade': 0,
            'max_grade': 0
        }
    
    min_grade = min(values)
    max_grade = max(values)
    
    # Générer les coupures
    step = (max_grade - min_grade) / 20 if max_grade > min_grade else 0.1
    cutoffs = np.arange(min_grade, max_grade + step, max(step, 0.0001))
    
    tonnages = []
    grades = []
    metals = []
    cutoff_labels = []
    
    for cutoff in cutoffs:
        cutoff_labels.append(f"{cutoff:.2f}")
        
        if method == 'above':
            filtered_blocks = [block for block in blocks if block.get('value', 0) >= cutoff]
        elif method == 'below':
            filtered_blocks = [block for block in blocks if block.get('value', 0) <= cutoff]
        elif method == 'between':
            filtered_blocks = [block for block in blocks if cutoff_min <= block.get('value', 0) <= cutoff_max]
            
            # Pour la méthode between, on n'a besoin que d'un seul résultat
            if cutoff > min_grade:
                continue
        
        if not filtered_blocks:
            tonnages.append(0)
            grades.append(0)
            metals.append(0)
            continue
        
        total_tonnage = 0
        total_metal = 0
        
        for block in filtered_blocks:
            if 'size_x' in block and 'size_y' in block and 'size_z' in block:
                block_volume = block['size_x'] * block['size_y'] * block['size_z']
                block_density = block.get('density', density_value) if density_method == "variable" else density_value
                block_tonnage = block_volume * block_density
                
                total_tonnage += block_tonnage
                total_metal += block_tonnage * block.get('value', 0)
        
        if total_tonnage > 0:
            avg_grade = total_metal / total_tonnage
        else:
            avg_grade = 0
        
        tonnages.append(total_tonnage)
        grades.append(avg_grade)
        metals.append(total_metal)
    
    return {
        'cutoffs': cutoff_labels,
        'tonnages': tonnages,
        'grades': grades,
        'metals': metals
    }, {
        'method': method,
        'min_grade': min_grade,
        'max_grade': max_grade
    }

# Fonctions de visualisation
def plot_3d_model_with_cubes(blocks, composites, envelope_bounds=None, block_scale=0.9, color_by='value'):
    fig = go.Figure()
    
    # Ajouter les composites
    if composites:
        x = [comp.get('X', 0) for comp in composites if 'X' in comp and 'Y' in comp and 'Z' in comp and 'VALUE' in comp]
        y = [comp.get('Y', 0) for comp in composites if 'X' in comp and 'Y' in comp and 'Z' in comp and 'VALUE' in comp]
        z = [comp.get('Z', 0) for comp in composites if 'X' in comp and 'Y' in comp and 'Z' in comp and 'VALUE' in comp]
        values = [comp.get('VALUE', 0) for comp in composites if 'X' in comp and 'Y' in comp and 'Z' in comp and 'VALUE' in comp]
        
        if x and y and z and values:
            composite_scatter = go.Scatter3d(
                x=x,
                y=y,
                z=z,
                mode='markers',
                marker=dict(
                    size=3,
                    color=values,
                    colorscale='Viridis',
                    opacity=0.8,
                    colorbar=dict(title="Teneur")
                ),
                text=[f"Teneur: {v:.3f}" for v in values],
                name='Composites'
            )
            fig.add_trace(composite_scatter)
    
    # Ajouter les blocs en tant que cubes
    if blocks:
        # Vérifier les clés nécessaires dans les blocs
        valid_blocks = [block for block in blocks 
                      if 'x' in block and 'y' in block and 'z' in block 
                      and 'size_x' in block and 'size_y' in block and 'size_z' in block 
                      and color_by in block]
        
        if not valid_blocks:
            st.warning("Aucun bloc valide à afficher.")
            return fig
        
        # Limiter le nombre de blocs pour éviter de surcharger la visualisation
        max_display_blocks = 2000
        if len(valid_blocks) > max_display_blocks:
            st.warning(f"Le modèle contient {len(valid_blocks)} blocs. Pour une meilleure performance, seuls {max_display_blocks} blocs sont affichés.")
            valid_blocks = valid_blocks[:max_display_blocks]
        
        # Créer des cubes pour chaque bloc (en utilisant Mesh3d)
        x_vals = []
        y_vals = []
        z_vals = []
        i_vals = []
        j_vals = []
        k_vals = []
        intensity = []
        
        for idx, block in enumerate(valid_blocks):
            # Créer les 8 sommets d'un cube
            x_size = block['size_x'] * block_scale / 2
            y_size = block['size_y'] * block_scale / 2
            z_size = block['size_z'] * block_scale / 2
            
            x0, y0, z0 = block['x'] - x_size, block['y'] - y_size, block['z'] - z_size
            x1, y1, z1 = block['x'] + x_size, block['y'] + y_size, block['z'] + z_size
            
            # Ajouter les sommets
            vertices = [
                (x0, y0, z0),  # 0
                (x1, y0, z0),  # 1
                (x1, y1, z0),  # 2
                (x0, y1, z0),  # 3
                (x0, y0, z1),  # 4
                (x1, y0, z1),  # 5
                (x1, y1, z1),  # 6
                (x0, y1, z1)   # 7
            ]
            
            # Ajouter les faces du cube (triangles)
            faces = [
                (0, 1, 2), (0, 2, 3),  # bottom
                (4, 5, 6), (4, 6, 7),  # top
                (0, 1, 5), (0, 5, 4),  # front
                (2, 3, 7), (2, 7, 6),  # back
                (0, 3, 7), (0, 7, 4),  # left
                (1, 2, 6), (1, 6, 5)   # right
            ]
            
            for v in vertices:
                x_vals.append(v[0])
                y_vals.append(v[1])
                z_vals.append(v[2])
                intensity.append(block[color_by])
            
            offset = idx * 8  # 8 sommets par cube
            for f in faces:
                i_vals.append(offset + f[0])
                j_vals.append(offset + f[1])
                k_vals.append(offset + f[2])
        
        if x_vals and y_vals and z_vals and i_vals and j_vals and k_vals and intensity:
            # Utiliser une échelle de couleur appropriée au type de valeur
            if color_by == 'value':
                colorscale = 'Viridis'
                colorbar_title = "Teneur"
                block_name = 'Blocs estimés'
            elif color_by == 'estimation_variance':
                colorscale = 'Reds'
                colorbar_title = "Variance"
                block_name = 'Variance d\'estimation'
            else:
                colorscale = 'Viridis'
                colorbar_title = color_by
                block_name = 'Blocs'
            
            block_mesh = go.Mesh3d(
                x=x_vals,
                y=y_vals,
                z=z_vals,
                i=i_vals,
                j=j_vals,
                k=k_vals,
                intensity=intensity,
                colorscale=colorscale,
                opacity=0.7,
                name=block_name,
                colorbar=dict(title=colorbar_title)
            )
            fig.add_trace(block_mesh)
    
    # Ajouter l'enveloppe (boîte transparente) si spécifiée
    if envelope_bounds:
        min_bounds = envelope_bounds['min']
        max_bounds = envelope_bounds['max']
        
        # Créer une boîte transparente représentant l'enveloppe
        x = [min_bounds['x'], max_bounds['x'], max_bounds['x'], min_bounds['x'], min_bounds['x'], max_bounds['x'], max_bounds['x'], min_bounds['x']]
        y = [min_bounds['y'], min_bounds['y'], max_bounds['y'], max_bounds['y'], min_bounds['y'], min_bounds['y'], max_bounds['y'], max_bounds['y']]
        z = [min_bounds['z'], min_bounds['z'], min_bounds['z'], min_bounds['z'], max_bounds['z'], max_bounds['z'], max_bounds['z'], max_bounds['z']]
        
        # Définir les indices pour former les faces de la boîte (12 triangles pour 6 faces)
        i = [0, 0, 0, 0, 4, 4, 4, 7, 7, 6, 6, 6]
        j = [1, 1, 3, 4, 5, 5, 7, 3, 6, 5, 2, 2]
        k = [2, 4, 7, 5, 1, 6, 6, 0, 3, 1, 3, 1]
        
        envelope_mesh = go.Mesh3d(
            x=x, y=y, z=z, i=i, j=j, k=k,
            opacity=0.2,
            color='green',
            name='Enveloppe'
        )
        fig.add_trace(envelope_mesh)
    
    # Mise en page améliorée
    fig.update_layout(
        scene=dict(
            xaxis_title='X (m)',
            yaxis_title='Y (m)',
            zaxis_title='Z (m)',
            aspectratio=dict(x=1, y=1, z=1),
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.2)
            ),
            # Améliorations visuelles
            xaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'),
            zaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)')
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        legend=dict(x=0, y=0.95, orientation='h', bgcolor='rgba(255, 255, 255, 0.7)'),
        template='plotly_white',  # Style de graphique plus épuré
    )
    
    return fig

def plot_histogram(values, title, color='steelblue'):
    if not values or len(values) <= 1:
        # Créer un graphique vide avec un message
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "Données insuffisantes pour l'histogramme", 
                horizontalalignment='center', verticalalignment='center',
                transform=ax.transAxes, fontsize=14)
        ax.set_title(title)
        return fig
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Calculer le nombre de bins (au moins 5)
    n_bins = max(5, int(1 + 3.322 * math.log10(len(values))))
    
    sns.histplot(values, bins=n_bins, kde=True, color=color, ax=ax)
    ax.set_title(title)
    ax.set_xlabel('Valeur')
    ax.set_ylabel('Fréquence')
    
    # Améliorations esthétiques
    ax.grid(True, linestyle='--', alpha=0.7)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    
    return fig

def plot_tonnage_grade(tonnage_data, plot_info=None):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Vérifier si les données sont valides
    if (not tonnage_data or 'cutoffs' not in tonnage_data or 'tonnages' not in tonnage_data or 'grades' not in tonnage_data or
        len(tonnage_data['cutoffs']) == 0 or len(tonnage_data['tonnages']) == 0 or len(tonnage_data['grades']) == 0):
        # Ajouter un texte indiquant l'absence de données
        fig.add_annotation(
            x=0.5, y=0.5,
            text="Données insuffisantes pour le graphique tonnage-teneur",
            showarrow=False,
            font=dict(size=14)
        )
        return fig
    
    if plot_info and plot_info.get('method') == 'between':
        # Pour la méthode 'between', on utilise un graphique à barres
        fig.add_trace(
            go.Bar(
                x=['Résultat'],
                y=[tonnage_data['tonnages'][0]],
                name='Tonnage',
                marker_color='rgb(53, 112, 193)'
            )
        )
        
        fig.add_trace(
            go.Bar(
                x=['Résultat'],
                y=[tonnage_data['grades'][0]],
                name='Teneur moyenne',
                marker_color='rgb(70, 157, 101)'
            ),
            secondary_y=True
        )
    else:
        # Pour les méthodes 'above' et 'below', on utilise un graphique en ligne
        fig.add_trace(
            go.Scatter(
                x=tonnage_data['cutoffs'],
                y=tonnage_data['tonnages'],
                name='Tonnage',
                fill='tozeroy',
                mode='lines',
                line=dict(color='rgb(53, 112, 193)', width=3)
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=tonnage_data['cutoffs'],
                y=tonnage_data['grades'],
                name='Teneur moyenne',
                mode='lines',
                line=dict(color='rgb(70, 157, 101)', width=3)
            ),
            secondary_y=True
        )
    
    # Mise en page améliorée
    fig.update_layout(
        title_text='Courbe Tonnage-Teneur',
        xaxis_title='Teneur de coupure',
        legend=dict(x=0, y=1.1, orientation='h', bgcolor='rgba(255, 255, 255, 0.7)'),
        plot_bgcolor='white',
        grid=dict(gridcolor='rgba(128, 128, 128, 0.2)'),
        template='plotly_white'
    )
    
    fig.update_yaxes(title_text='Tonnage (t)', secondary_y=False, gridcolor='rgba(128, 128, 128, 0.2)')
    fig.update_yaxes(title_text='Teneur moyenne', secondary_y=True, gridcolor='rgba(128, 128, 128, 0.2)')
    
    return fig

def plot_metal_content(tonnage_data, plot_info=None):
    fig = go.Figure()
    
    # Vérifier si les données sont valides
    if (not tonnage_data or 'cutoffs' not in tonnage_data or 'metals' not in tonnage_data or
        len(tonnage_data['cutoffs']) == 0 or len(tonnage_data['metals']) == 0):
        # Ajouter un texte indiquant l'absence de données
        fig.add_annotation(
            x=0.5, y=0.5,
            text="Données insuffisantes pour le graphique de métal contenu",
            showarrow=False,
            font=dict(size=14)
        )
        return fig
    
    if plot_info and plot_info.get('method') == 'between':
        # Pour la méthode 'between', on utilise un graphique à barres
        if len(tonnage_data['metals']) > 0:
            fig.add_trace(
                go.Bar(
                    x=['Résultat'],
                    y=[tonnage_data['metals'][0]],
                    name='Métal contenu',
                    marker_color='rgb(172, 98, 168)'
                )
            )
    else:
        # Pour les méthodes 'above' et 'below', on utilise un graphique en ligne
        fig.add_trace(
            go.Scatter(
                x=tonnage_data['cutoffs'],
                y=tonnage_data['metals'],
                name='Métal contenu',
                fill='tozeroy',
                mode='lines',
                line=dict(color='rgb(172, 98, 168)', width=3)
            )
        )
    
    # Mise en page améliorée
    fig.update_layout(
        title_text='Métal contenu',
        xaxis_title='Teneur de coupure',
        yaxis_title='Métal contenu',
        plot_bgcolor='white',
        grid=dict(gridcolor='rgba(128, 128, 128, 0.2)'),
        template='plotly_white'
    )
    
    return fig

# Interface utilisateur Streamlit
# Sidebar - Chargement des données et paramètres
with st.sidebar:
    st.markdown("## ⚙️ Paramètres d'estimation")
    
    # Nom du projet
    project_name = st.text_input("Nom du projet", "Projet Minier")
    
    uploaded_file = st.file_uploader("Fichier CSV des composites", type=["csv"])
    
    if uploaded_file:
        try:
            # Section pour la conversion CSV
            st.write("### Options de lecture CSV")
            
            # Chargement automatique avec détection des paramètres
            with st.spinner("Analyse du fichier CSV en cours..."):
                if 'csv_params' not in st.session_state:
                    best_df, best_params = attempt_csv_loading(uploaded_file)
                    st.session_state.csv_params = best_params
                    df = best_df
                    
                    if df is None:
                        st.error("Impossible de charger le fichier CSV. Veuillez vérifier le format.")
                        st.stop()
                else:
                    # Utiliser les paramètres déjà détectés
                    params = st.session_state.csv_params
                    uploaded_file.seek(0)
                    df = pd.read_csv(
                        uploaded_file, 
                        sep=params['separator'], 
                        decimal=params['decimal'], 
                        encoding=params['encoding'],
                        low_memory=False,
                        on_bad_lines='warn'
                    )
            
            # Afficher les paramètres détectés automatiquement
            col1, col2, col3 = st.columns(3)
            with col1:
                selected_encoding = st.selectbox(
                    "Encodage du fichier", 
                    options=['utf-8', 'latin1', 'iso-8859-1', 'cp1252'],
                    index=['utf-8', 'latin1', 'iso-8859-1', 'cp1252'].index(st.session_state.csv_params['encoding'])
                )
            
            with col2:
                separator_options = [',', ';', '\t', '|']
                separator_names = ["Virgule (,)", "Point-virgule (;)", "Tabulation", "Pipe (|)"]
                selected_separator = st.selectbox(
                    "Séparateur", 
                    options=separator_options, 
                    index=separator_options.index(st.session_state.csv_params['separator']),
                    format_func=lambda x: separator_names[separator_options.index(x)]
                )
            
            with col3:
                decimal_options = ['.', ',']
                selected_decimal = st.selectbox(
                    "Séparateur décimal", 
                    options=decimal_options,
                    index=decimal_options.index(st.session_state.csv_params['decimal']),
                    format_func=lambda x: "Point (.)" if x == '.' else "Virgule (,)"
                )
            
            # Recharger avec les paramètres sélectionnés si différents
            if (selected_encoding != st.session_state.csv_params['encoding'] or
                selected_separator != st.session_state.csv_params['separator'] or
                selected_decimal != st.session_state.csv_params['decimal']):
                
                uploaded_file.seek(0)
                df = pd.read_csv(
                    uploaded_file, 
                    sep=selected_separator, 
                    decimal=selected_decimal, 
                    encoding=selected_encoding,
                    low_memory=False,
                    on_bad_lines='warn'
                )
                
                # Mettre à jour les paramètres stockés
                st.session_state.csv_params = {
                    'encoding': selected_encoding,
                    'separator': selected_separator, 
                    'decimal': selected_decimal
                }
            
            st.success(f"{len(df)} lignes chargées")
            
            # Afficher un aperçu des données
            with st.expander("Aperçu des données chargées", expanded=False):
                st.write("Aperçu des premières lignes :", df.head())
                st.write("Types de données :", df.dtypes)
                st.write("Nombre de valeurs non-nulles :", df.count())
            
        except Exception as e:
            st.error(f"Erreur lors du chargement du fichier: {str(e)}")
            st.stop()
        
        # Vérifier si le DataFrame est valide
        if df is None or df.empty:
            st.error("Le fichier CSV ne contient pas de données valides.")
            st.stop()
        
        # Mappage des colonnes
        st.markdown("### 📊 Mappage des colonnes")
        
        try:
            # Sélection des colonnes
            col_x = st.selectbox("Colonne X", options=df.columns, 
                                index=df.columns.get_loc('X') if 'X' in df.columns else 0)
            col_y = st.selectbox("Colonne Y", options=df.columns, 
                                index=df.columns.get_loc('Y') if 'Y' in df.columns else 0)
            col_z = st.selectbox("Colonne Z", options=df.columns, 
                                index=df.columns.get_loc('Z') if 'Z' in df.columns else 0)
            
            # Colonne de teneur
            value_col_index = (df.columns.get_loc('VALUE') if 'VALUE' in df.columns else 0)
            col_value = st.selectbox("Colonne Teneur", options=df.columns, index=value_col_index)
        except Exception as e:
            st.error(f"Erreur lors du mappage des colonnes: {str(e)}")
            st.stop()
        
        # Option pour la densité
        st.markdown("### 🧮 Densité")
        density_options = ["Constante", "Variable (colonne)"]
        density_method = st.radio("Méthode de densité", options=density_options)
        
        if density_method == "Constante":
            density_value = st.number_input("Densité (t/m³)", min_value=0.1, value=2.7, step=0.1)
            density_column = None
        else:
            density_column = st.selectbox("Colonne Densité", options=df.columns, 
                                        index=df.columns.get_loc('DENSITY') if 'DENSITY' in df.columns else 0)
            if density_column in df.columns:
                st.info(f"Densité moyenne des échantillons: {df[density_column].mean():.2f} t/m³")
        
        # Filtres optionnels
        st.markdown("### 🔍 Filtrage")
        
        domain_options = ['-- Aucun --'] + list(df.columns)
        domain_index = domain_options.index('DOMAIN') if 'DOMAIN' in domain_options else 0
        col_domain = st.selectbox("Colonne de domaine", options=domain_options, index=domain_index)
        
        # Si un domaine est sélectionné
        domain_filter_value = None
        if col_domain != '-- Aucun --':
            domain_filter_type = st.selectbox("Type de filtre", options=["=", "!=", "IN", "NOT IN"])
            
            if domain_filter_type in ["=", "!="]:
                unique_values = df[col_domain].dropna().unique()
                if len(unique_values) > 0:
                    # Utiliser une liste déroulante pour sélectionner une valeur unique
                    domain_filter_value = st.selectbox("Valeur", options=unique_values)
                else:
                    domain_filter_value = st.text_input("Valeur")
            else:
                domain_values = df[col_domain].dropna().unique()
                domain_filter_value = st.multiselect("Valeurs", options=domain_values)
        
        # Enveloppe
        st.markdown("### 📦 Enveloppe")
        
        use_envelope = st.checkbox("Utiliser une enveloppe", value=True)
        
        if use_envelope:
            try:
                col1, col2 = st.columns(2)
                
                # Valeurs par défaut pour les limites min/max
                default_min_x = float(df[col_x].min()) if pd.api.types.is_numeric_dtype(df[col_x]) else 0
                default_min_y = float(df[col_y].min()) if pd.api.types.is_numeric_dtype(df[col_y]) else 0
                default_min_z = float(df[col_z].min()) if pd.api.types.is_numeric_dtype(df[col_z]) else 0
                default_max_x = float(df[col_x].max()) if pd.api.types.is_numeric_dtype(df[col_x]) else 100
                default_max_y = float(df[col_y].max()) if pd.api.types.is_numeric_dtype(df[col_y]) else 100
                default_max_z = float(df[col_z].max()) if pd.api.types.is_numeric_dtype(df[col_z]) else 100
                
                with col1:
                    st.markdown("**Minimum**")
                    min_x = st.number_input("Min X", value=default_min_x, format="%.2f")
                    min_y = st.number_input("Min Y", value=default_min_y, format="%.2f")
                    min_z = st.number_input("Min Z", value=default_min_z, format="%.2f")
                
                with col2:
                    st.markdown("**Maximum**")
                    max_x = st.number_input("Max X", value=default_max_x, format="%.2f")
                    max_y = st.number_input("Max Y", value=default_max_y, format="%.2f")
                    max_z = st.number_input("Max Z", value=default_max_z, format="%.2f")
                
                envelope_bounds = {
                    'min': {'x': min_x, 'y': min_y, 'z': min_z},
                    'max': {'x': max_x, 'y': max_y, 'z': max_z}
                }
                
                st.session_state.envelope_bounds = envelope_bounds
                
                # Afficher les dimensions
                st.info(f"📏 Dimensions de l'enveloppe: {max_x-min_x:.1f} × {max_y-min_y:.1f} × {max_z-min_z:.1f} m")
            except Exception as e:
                st.error(f"Erreur lors de la création de l'enveloppe: {str(e)}")
                st.session_state.envelope_bounds = None
        
        st.session_state.use_envelope = use_envelope
    
    # Paramètres du krigeage
    st.markdown("### 📈 Variogramme")
    
    # Type de variogramme
    variogram_type = st.selectbox(
        "Type de variogramme", 
        options=["spherical", "exponential", "gaussian"],
        format_func=lambda x: "Sphérique" if x == "spherical" else "Exponentiel" if x == "exponential" else "Gaussien"
    )
    
    # Paramètres du variogramme
    col1, col2 = st.columns(2)
    
    with col1:
        nugget = st.number_input("Effet pépite", min_value=0.0, value=0.0, step=0.01)
        sill = st.number_input("Palier", min_value=0.01, value=1.0, step=0.1)
    
    with col2:
        range_val = st.number_input("Portée (m)", min_value=1.0, value=100.0, step=10.0)
    
    # Anisotropie
    st.markdown("### 🧭 Anisotropie")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        anisotropy_x = st.number_input("X", min_value=0.1, value=1.0, step=0.1)
    
    with col2:
        anisotropy_y = st.number_input("Y", min_value=0.1, value=1.0, step=0.1)
    
    with col3:
        anisotropy_z = st.number_input("Z", min_value=0.1, value=0.5, step=0.1)
    
    # Paramètres du modèle de blocs
    st.markdown("### 🧊 Modèle de blocs")
    
    st.markdown("**Taille des blocs (m)**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        block_size_x = st.number_input("X", min_value=1, value=10, step=1)
    
    with col2:
        block_size_y = st.number_input("Y", min_value=1, value=10, step=1)
    
    with col3:
        block_size_z = st.number_input("Z", min_value=1, value=5, step=1)
    
    st.markdown("**Rayon de recherche (m)**")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_radius_x = st.number_input("X ", min_value=1, value=50, step=1)
    
    with col2:
        search_radius_y = st.number_input("Y ", min_value=1, value=50, step=1)
    
    with col3:
        search_radius_z = st.number_input("Z ", min_value=1, value=25, step=1)
    
    st.markdown("**Conditions d'estimation**")
    min_samples = st.number_input("Nombre min d'échantillons", min_value=1, value=2, step=1)
    max_samples = st.number_input("Nombre max d'échantillons", min_value=1, value=12, step=1)

# Traitement des données
if uploaded_file:
    # Diagnostic des données
    st.markdown("## 🔍 Validation des données")
    
    try:
        # Préparer le filtrage par domaine
        domain_filter = None
        if col_domain != '-- Aucun --' and domain_filter_value is not None:
            domain_filter = (domain_filter_type, domain_filter_value)
        
        # Nettoyer et préparer les données
        cleaned_df, cleaning_stats = clean_and_prepare_data(
            df, col_x, col_y, col_z, col_value, col_domain, domain_filter
        )
        
        # Afficher les statistiques de nettoyage
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Graphique montrant l'impact des étapes de nettoyage
            fig = plot_data_cleaning_steps(cleaning_stats)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("### Détails du nettoyage")
            st.dataframe(cleaning_stats, use_container_width=True, hide_index=True)
            
            final_count = cleaning_stats['Nombre de lignes'].iloc[-1]
            initial_count = cleaning_stats['Nombre de lignes'].iloc[0]
            percent_kept = (final_count / initial_count * 100) if initial_count > 0 else 0
            
            st.metric(
                "Échantillons valides", 
                f"{final_count}", 
                f"{percent_kept:.1f}% des données originales"
            )
        
        # Vérifier s'il y a des lignes valides après nettoyage
        if len(cleaned_df) == 0:
            st.error("Aucun échantillon valide après nettoyage. Vérifiez vos données et filtres.")
            st.stop()
        
        # Convertir en liste de composites
        composites_data = df_to_composites(
            cleaned_df, col_x, col_y, col_z, col_value, 
            col_domain, density_column if density_method == "Variable (colonne)" else None
        )
        
        # Afficher un aperçu des composites
        with st.expander("📊 Aperçu des composites", expanded=False):
            st.markdown("### 5 premiers composites")
            composites_preview = pd.DataFrame(composites_data[:5])
            st.write(composites_preview)
            
            st.markdown("### Statistiques des composites")
            composite_values = [comp['VALUE'] for comp in composites_data]
            
            col_stats1, col_stats2 = st.columns(2)
            
            with col_stats1:
                st.write(f"**Nombre total de composites** : {len(composites_data)}")
                if len(composite_values) > 0:
                    st.write(f"**Teneur minimale** : {min(composite_values):.3f}")
                    st.write(f"**Teneur maximale** : {max(composite_values):.3f}")
                    st.write(f"**Teneur moyenne** : {sum(composite_values)/len(composite_values):.3f}")
            
            with col_stats2:
                # Afficher un histogramme miniature
                if len(composite_values) > 1:
                    fig, ax = plt.subplots(figsize=(6, 3))
                    n_bins = min(20, max(5, int(1 + 3.322 * math.log10(len(composite_values)))))
                    ax.hist(composite_values, bins=n_bins, color='steelblue', alpha=0.7)
                    ax.set_title("Distribution des teneurs")
                    ax.set_xlabel("Teneur")
                    ax.set_ylabel("Fréquence")
                    st.pyplot(fig)
        
        # Validation finale
        if len(composites_data) < 2:
            st.warning("⚠️ Un minimum de 2 composites est recommandé pour l'estimation. Les résultats pourraient ne pas être fiables.")
        
        # Succès!
        st.success(f"✅ Traitement des données réussi : {len(composites_data)} composites valides prêts pour l'estimation!")
        
    except Exception as e:
        st.error(f"Erreur lors du traitement des données : {str(e)}")
        show_detailed_error("Erreur détaillée", e)
        st.stop()
    
    # Afficher les statistiques des composites
    composite_values = [comp['VALUE'] for comp in composites_data]
    composite_stats = calculate_stats(composite_values)
    
    # Créer le modèle de variogramme
    variogram_model = {
        'type': variogram_type,
        'nugget': nugget,
        'sill': sill,
        'range': range_val,
        'total_sill': nugget + sill
    }
    
    # Enregistrer le modèle de variogramme dans la session
    st.session_state.variogram_model = variogram_model
    
    # Onglets principaux
    tabs = st.tabs(["📊 Modèle 3D", "📈 Statistiques", "📉 Tonnage-Teneur"])
    
    with tabs[0]:  # Modèle 3D
        st.markdown("## 📊 Modèle de blocs 3D")
        
        col1, col2 = st.columns([3, 1])
        
        with col2:
            create_model_button = st.button("Créer le modèle de blocs", type="primary", use_container_width=True)
            
            if "empty_blocks" in st.session_state and st.session_state.empty_blocks:
                estimate_button = st.button("Estimer par krigeage ordinaire", type="primary", use_container_width=True)
            
            # Options d'affichage
            st.markdown("### 🔍 Options d'affichage")
            show_composites = st.checkbox("Afficher les composites", value=True)
            show_blocks = st.checkbox("Afficher les blocs", value=True)
            show_envelope = st.checkbox("Afficher l'enveloppe", value=True if 'envelope_bounds' in st.session_state and st.session_state.envelope_bounds else False)
            
            # Taille des cubes
            block_scale = st.slider("Taille des blocs (échelle)", min_value=0.1, max_value=1.0, value=0.9, step=0.05)
            
            # Option de coloration
            if "estimated_blocks" in st.session_state:
                color_by = st.radio(
                    "Colorer par", 
                    options=["value", "estimation_variance"],
                    format_func=lambda x: "Teneur" if x == "value" else "Variance d'estimation"
                )
            else:
                color_by = "value"
        
        with col1:
            try:
                if create_model_button:
                    # Créer le modèle de blocs vide
                    block_sizes = {'x': block_size_x, 'y': block_size_y, 'z': block_size_z}
                    envelope_bounds = st.session_state.envelope_bounds if 'envelope_bounds' in st.session_state else None
                    use_envelope = st.session_state.use_envelope if 'use_envelope' in st.session_state else False
                    
                    empty_blocks, model_bounds = create_block_model(
                        composites_data, 
                        block_sizes, 
                        envelope_bounds, 
                        use_envelope
                    )
                    
                    if not empty_blocks:
                        st.error("Impossible de créer le modèle de blocs. Vérifiez vos paramètres et données.")
                    else:
                        st.session_state.empty_blocks = empty_blocks
                        st.session_state.model_bounds = model_bounds
                        
                        st.success(f"✅ Modèle créé avec {len(empty_blocks)} blocs")
                        
                        # Afficher le modèle 3D
                        envelope_bounds_to_show = envelope_bounds if show_envelope and envelope_bounds else None
                        fig = plot_3d_model_with_cubes(
                            [],
                            composites_data if show_composites else [],
                            envelope_bounds_to_show,
                            block_scale
                        )
                        st.plotly_chart(fig, use_container_width=True, height=600)
                
                elif "empty_blocks" in st.session_state and estimate_button:
                    # Paramètres pour le krigeage
                    kriging_params = {
                        'anisotropy': {'x': anisotropy_x, 'y': anisotropy_y, 'z': anisotropy_z}
                    }
                    
                    search_params = {
                        'x': search_radius_x,
                        'y': search_radius_y,
                        'z': search_radius_z,
                        'min_samples': min_samples,
                        'max_samples': max_samples
                    }
                    
                    # Détermine la méthode de densité
                    if density_method == "Variable (colonne)":
                        density_method_str = "variable"
                        density_value_num = None
                    else:
                        density_method_str = "constant"
                        density_value_num = density_value
                    
                    # Estimer le modèle
                    estimated_blocks = estimate_block_model_kriging(
                        st.session_state.empty_blocks, 
                        composites_data,
                        kriging_params,
                        search_params,
                        variogram_model,
                        density_method_str,
                        density_value_num
                    )
                    
                    if not estimated_blocks:
                        st.error("L'estimation n'a pas produit de blocs. Vérifiez vos paramètres.")
                    else:
                        st.session_state.estimated_blocks = estimated_blocks
                        
                        # Stocker les paramètres pour les rapports futurs
                        st.session_state.kriging_params = kriging_params
                        st.session_state.search_params = search_params
                        st.session_state.block_sizes = {'x': block_size_x, 'y': block_size_y, 'z': block_size_z}
                        st.session_state.density_method = density_method_str
                        st.session_state.density_value = density_value_num if density_method_str == "constant" else None
                        st.session_state.density_column = density_column if density_method_str == "variable" else None
                        st.session_state.project_name = project_name
                        
                        st.success(f"✅ Estimation terminée, {len(estimated_blocks)} blocs estimés")
                        
                        # Afficher le modèle estimé
                        envelope_bounds_to_show = st.session_state.envelope_bounds if show_envelope and 'envelope_bounds' in st.session_state else None
                        fig = plot_3d_model_with_cubes(
                            estimated_blocks if show_blocks else [],
                            composites_data if show_composites else [],
                            envelope_bounds_to_show,
                            block_scale,
                            color_by
                        )
                        st.plotly_chart(fig, use_container_width=True, height=600)
                        
                        # Section d'export
                        st.markdown("### 💾 Exporter les résultats")
                        
                        # Export du modèle de blocs en CSV
                        if st.button("Exporter modèle de blocs (CSV)", type="primary", use_container_width=True):
                            # Créer un DataFrame pour l'export
                            export_df = pd.DataFrame(estimated_blocks)
                            
                            # Renommer les colonnes pour correspondre au format d'origine
                            export_df = export_df.rename(columns={
                                'x': 'X', 'y': 'Y', 'z': 'Z', 'value': 'VALUE',
                                'size_x': 'SIZE_X', 'size_y': 'SIZE_Y', 'size_z': 'SIZE_Z',
                                'density': 'DENSITY', 'estimation_variance': 'KRIG_VAR'
                            })
                            
                            # Ajouter des informations supplémentaires
                            export_df['VOLUME'] = export_df['SIZE_X'] * export_df['SIZE_Y'] * export_df['SIZE_Z']
                            export_df['TONNAGE'] = export_df['VOLUME'] * export_df['DENSITY']
                            export_df['METAL_CONTENT'] = export_df['VALUE'] * export_df['TONNAGE']
                            
                            # Créer le lien de téléchargement
                            csv = export_df.to_csv(index=False)
                            st.download_button(
                                label="Télécharger CSV",
                                data=csv,
                                file_name=f"{project_name.replace(' ', '_')}_modele_blocs_krigeage.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                
                elif "estimated_blocks" in st.session_state:
                    # Afficher le modèle estimé déjà calculé
                    envelope_bounds_to_show = st.session_state.envelope_bounds if show_envelope and 'envelope_bounds' in st.session_state else None
                    fig = plot_3d_model_with_cubes(
                        st.session_state.estimated_blocks if show_blocks else [],
                        composites_data if show_composites else [],
                        envelope_bounds_to_show,
                        block_scale,
                        color_by
                    )
                    st.plotly_chart(fig, use_container_width=True, height=600)
                    
                    # Section d'export
                    st.markdown("### 💾 Exporter les résultats")
                    
                    # Export du modèle de blocs en CSV
                    if st.button("Exporter modèle de blocs (CSV)", type="primary", use_container_width=True):
                        # Créer un DataFrame pour l'export
                        export_df = pd.DataFrame(st.session_state.estimated_blocks)
                        
                        # Renommer les colonnes pour correspondre au format d'origine
                        export_df = export_df.rename(columns={
                            'x': 'X', 'y': 'Y', 'z': 'Z', 'value': 'VALUE',
                            'size_x': 'SIZE_X', 'size_y': 'SIZE_Y', 'size_z': 'SIZE_Z',
                            'density': 'DENSITY', 'estimation_variance': 'KRIG_VAR'
                        })
                        
                        # Ajouter des informations supplémentaires
                        export_df['VOLUME'] = export_df['SIZE_X'] * export_df['SIZE_Y'] * export_df['SIZE_Z']
                        export_df['TONNAGE'] = export_df['VOLUME'] * export_df['DENSITY']
                        export_df['METAL_CONTENT'] = export_df['VALUE'] * export_df['TONNAGE']
                        
                        # Créer le lien de téléchargement
                        csv = export_df.to_csv(index=False)
                        st.download_button(
                            label="Télécharger CSV",
                            data=csv,
                            file_name=f"{project_name.replace(' ', '_')}_modele_blocs_krigeage.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                
                else:
                    # Afficher seulement les composites si aucun modèle n'est créé
                    envelope_bounds_to_show = st.session_state.envelope_bounds if show_envelope and 'envelope_bounds' in st.session_state else None
                    fig = plot_3d_model_with_cubes(
                        [],
                        composites_data if show_composites else [],
                        envelope_bounds_to_show,
                        block_scale
                    )
                    st.plotly_chart(fig, use_container_width=True, height=600)
            except Exception as e:
                st.error(f"Erreur dans l'onglet Modèle 3D: {str(e)}")
                show_detailed_error("Erreur détaillée", e)
    
    with tabs[1]:  # Statistiques
        st.markdown("## 📈 Analyse statistique")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Statistiques des composites")
            
            if composite_stats['count'] > 0:
                stats_df = pd.DataFrame({
                    'Paramètre': ['Nombre d\'échantillons', 'Minimum', 'Maximum', 'Moyenne', 'Médiane', 'Écart-type', 'CV'],
                    'Valeur': [
                        composite_stats['count'],
                        f"{composite_stats['min']:.3f}",
                        f"{composite_stats['max']:.3f}",
                        f"{composite_stats['mean']:.3f}",
                        f"{composite_stats['median']:.3f}",
                        f"{composite_stats['stddev']:.3f}",
                        f"{composite_stats['cv']:.3f}"
                    ]
                })
                
                st.dataframe(stats_df, hide_index=True, use_container_width=True)
                
                st.markdown("### Histogramme des composites")
                fig = plot_histogram(composite_values, f"Distribution des teneurs des composites ({col_value})", "darkblue")
                st.pyplot(fig)
            else:
                st.warning("Aucune donnée valide pour calculer les statistiques des composites.")
            
            # Statistiques de densité si disponible
            if density_method == "Variable (colonne)" and density_column:
                st.markdown("### Statistiques de densité")
                density_values = [comp.get('DENSITY') for comp in composites_data if 'DENSITY' in comp]
                if density_values:
                    density_stats = calculate_stats(density_values)
                    
                    density_stats_df = pd.DataFrame({
                        'Paramètre': ['Nombre d\'échantillons', 'Minimum', 'Maximum', 'Moyenne', 'Médiane', 'Écart-type', 'CV'],
                        'Valeur': [
                            density_stats['count'],
                            f"{density_stats['min']:.3f}",
                            f"{density_stats['max']:.3f}",
                            f"{density_stats['mean']:.3f}",
                            f"{density_stats['median']:.3f}",
                            f"{density_stats['stddev']:.3f}",
                            f"{density_stats['cv']:.3f}"
                        ]
                    })
                    
                    st.dataframe(density_stats_df, hide_index=True, use_container_width=True)
            
            # Informations sur le variogramme
            st.markdown("### Paramètres du variogramme")
            variogram_df = pd.DataFrame({
                'Paramètre': ['Type', 'Effet pépite', 'Palier', 'Portée', 'Palier total'],
                'Valeur': [
                    variogram_model['type'],
                    f"{variogram_model['nugget']:.3f}",
                    f"{variogram_model['sill']:.3f}",
                    f"{variogram_model['range']:.1f} m",
                    f"{variogram_model['total_sill']:.3f}"
                ]
            })
            st.dataframe(variogram_df, hide_index=True, use_container_width=True)
        
        with col2:
            if "estimated_blocks" in st.session_state and st.session_state.estimated_blocks:
                block_values = [block.get('value', 0) for block in st.session_state.estimated_blocks]
                block_stats = calculate_stats(block_values)
                
                st.markdown("### Statistiques du modèle de blocs")
                
                stats_df = pd.DataFrame({
                    'Paramètre': ['Nombre de blocs', 'Minimum', 'Maximum', 'Moyenne', 'Médiane', 'Écart-type', 'CV'],
                    'Valeur': [
                        block_stats['count'],
                        f"{block_stats['min']:.3f}",
                        f"{block_stats['max']:.3f}",
                        f"{block_stats['mean']:.3f}",
                        f"{block_stats['median']:.3f}",
                        f"{block_stats['stddev']:.3f}",
                        f"{block_stats['cv']:.3f}"
                    ]
                })
                
                st.dataframe(stats_df, hide_index=True, use_container_width=True)
                
                st.markdown("### Histogramme du modèle de blocs")
                fig = plot_histogram(block_values, f"Distribution des teneurs du modèle de blocs ({col_value})", "teal")
                st.pyplot(fig)
                
                # Statistiques de la variance d'estimation
                variance_values = [block.get('estimation_variance', 0) for block in st.session_state.estimated_blocks if 'estimation_variance' in block]
                if variance_values:
                    st.markdown("### Variance d'estimation")
                    variance_stats = calculate_stats(variance_values)
                    
                    variance_df = pd.DataFrame({
                        'Paramètre': ['Minimum', 'Maximum', 'Moyenne', 'Médiane', 'Écart-type'],
                        'Valeur': [
                            f"{variance_stats['min']:.4f}",
                            f"{variance_stats['max']:.4f}",
                            f"{variance_stats['mean']:.4f}",
                            f"{variance_stats['median']:.4f}",
                            f"{variance_stats['stddev']:.4f}"
                        ]
                    })
                    
                    st.dataframe(variance_df, hide_index=True, use_container_width=True)
                    
                    st.markdown("### Histogramme de la variance d'estimation")
                    fig = plot_histogram(variance_values, "Distribution de la variance d'estimation", "salmon")
                    st.pyplot(fig)
                
                # Résumé des statistiques globales
                st.markdown("### Résumé global")
                
                # Vérifier les clés nécessaires
                if (all(key in st.session_state.estimated_blocks[0] for key in ['size_x', 'size_y', 'size_z']) and 
                    block_stats['count'] > 0):
                    block_volume = st.session_state.estimated_blocks[0]['size_x'] * st.session_state.estimated_blocks[0]['size_y'] * st.session_state.estimated_blocks[0]['size_z']
                    total_volume = len(st.session_state.estimated_blocks) * block_volume
                    
                    # Calcul du tonnage avec densité variable ou constante
                    if density_method == "Variable (colonne)":
                        total_tonnage = sum(block.get('density', density_value) * block_volume for block in st.session_state.estimated_blocks)
                        avg_density = total_tonnage / total_volume if total_volume > 0 else density_value
                    else:
                        avg_density = density_value
                        total_tonnage = total_volume * avg_density
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric("Nombre de blocs", f"{len(st.session_state.estimated_blocks):,}")
                        st.metric(f"Teneur moyenne {col_value}", f"{block_stats['mean']:.3f}")
                    
                    with col2:
                        st.metric("Volume total (m³)", f"{total_volume:,.0f}")
                        st.metric("Tonnage total (t)", f"{total_tonnage:,.0f}")
                else:
                    st.warning("Données insuffisantes pour calculer les métriques globales.")
            else:
                st.info("Veuillez d'abord créer et estimer le modèle de blocs pour afficher les statistiques.")
    
    with tabs[2]:  # Tonnage-Teneur
        st.markdown("## 📉 Analyse Tonnage-Teneur")
        
        if "estimated_blocks" in st.session_state and st.session_state.estimated_blocks:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            
            with col1:
                cutoff_method = st.selectbox(
                    "Méthode de coupure",
                    options=["above", "below", "between"],
                    format_func=lambda x: "Teneur ≥ Coupure" if x == "above" else "Teneur ≤ Coupure" if x == "below" else "Entre deux teneurs"
                )
            
            cutoff_value = None
            cutoff_min = None
            cutoff_max = None
            
            if cutoff_method == "between":
                with col2:
                    cutoff_min = st.number_input("Teneur min", min_value=0.0, value=0.5, step=0.1)
                
                with col3:
                    cutoff_max = st.number_input("Teneur max", min_value=cutoff_min, value=1.0, step=0.1)
            else:
                with col2:
                    cutoff_value = st.number_input("Teneur de coupure", min_value=0.0, value=0.5, step=0.1)
            
            with col4:
                if st.button("Calculer", type="primary", use_container_width=True):
                    try:
                        # Détermine la méthode de densité
                        density_method_str = st.session_state.density_method if 'density_method' in st.session_state else "constant"
                        density_value_num = st.session_state.density_value if 'density_value' in st.session_state else density_value
                        
                        # Calculer les données tonnage-teneur
                        tonnage_data, plot_info = calculate_tonnage_grade(
                            st.session_state.estimated_blocks,
                            density_method_str,
                            density_value_num,
                            cutoff_method,
                            cutoff_value,
                            cutoff_min,
                            cutoff_max
                        )
                        
                        st.session_state.tonnage_data = tonnage_data
                        st.session_state.plot_info = plot_info
                    except Exception as e:
                        st.error(f"Erreur lors du calcul tonnage-teneur: {str(e)}")
                        show_detailed_error("Erreur détaillée", e)
            
            if "tonnage_data" in st.session_state:
                col1, col2 = st.columns(2)
                
                with col1:
                    # Graphique Tonnage-Teneur
                    fig = plot_tonnage_grade(st.session_state.tonnage_data, st.session_state.plot_info)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Graphique Métal contenu
                    fig = plot_metal_content(st.session_state.tonnage_data, st.session_state.plot_info)
                    st.plotly_chart(fig, use_container_width=True)
                
                # Tableau des résultats
                st.markdown("### 📋 Résultats détaillés")
                
                # Vérifier que les données existent
                if ('plot_info' in st.session_state and 'tonnage_data' in st.session_state and
                    'cutoffs' in st.session_state.tonnage_data and 'tonnages' in st.session_state.tonnage_data and 
                    'grades' in st.session_state.tonnage_data and 'metals' in st.session_state.tonnage_data):
                    
                    if st.session_state.plot_info.get('method') == 'between':
                        # Pour la méthode between, afficher un seul résultat
                        if len(st.session_state.tonnage_data['tonnages']) > 0:
                            result_df = pd.DataFrame({
                                'Coupure': [f"{cutoff_min:.2f} - {cutoff_max:.2f}"],
                                'Tonnage (t)': [st.session_state.tonnage_data['tonnages'][0]],
                                'Teneur moyenne': [st.session_state.tonnage_data['grades'][0]],
                                'Métal contenu': [st.session_state.tonnage_data['metals'][0]]
                            })
                            st.dataframe(result_df, hide_index=True, use_container_width=True)
                        else:
                            st.warning("Aucun résultat pour cette coupure.")
                    else:
                        # Pour les méthodes above et below, afficher la courbe complète
                        result_df = pd.DataFrame({
                            'Coupure': st.session_state.tonnage_data['cutoffs'],
                            'Tonnage (t)': st.session_state.tonnage_data['tonnages'],
                            'Teneur moyenne': st.session_state.tonnage_data['grades'],
                            'Métal contenu': st.session_state.tonnage_data['metals']
                        })
                        st.dataframe(result_df, hide_index=True, use_container_width=True)
                else:
                    st.warning("Données tonnage-teneur incomplètes.")
                
                # Export des résultats
                st.markdown("### 💾 Exporter les résultats")
                
                # Export Excel
                if st.button("Exporter en Excel", type="primary", use_container_width=True):
                    try:
                        # Créer un buffer pour le fichier Excel
                        output = io.BytesIO()
                        
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            # Écrire les données tonnage-teneur
                            result_df.to_excel(writer, sheet_name='Tonnage-Teneur', index=False)
                            
                            # Ajouter une feuille pour les paramètres
                            density_info = f"Variable (colonne {density_column})" if density_method == "Variable (colonne)" else f"Constante ({density_value} t/m³)"
                            
                            param_df = pd.DataFrame({
                                'Paramètre': [
                                    'Méthode de coupure', 
                                    'Méthode d\'estimation',
                                    'Type de variogramme',
                                    'Effet pépite',
                                    'Palier',
                                    'Portée',
                                    'Taille des blocs (m)',
                                    'Densité',
                                    'Date d\'exportation'
                                ],
                                'Valeur': [
                                    "Teneur ≥ Coupure" if cutoff_method == "above" else "Teneur ≤ Coupure" if cutoff_method == "below" else f"Entre {cutoff_min} et {cutoff_max}",
                                    'Krigeage ordinaire',
                                    variogram_type,
                                    nugget,
                                    sill,
                                    range_val,
                                    f"{block_size_x} × {block_size_y} × {block_size_z}",
                                    density_info,
                                    pd.Timestamp.now().strftime('%Y-%m-%d')
                                ]
                            })
                            param_df.to_excel(writer, sheet_name='Paramètres', index=False)
                        
                        # Télécharger le fichier
                        output.seek(0)
                        st.download_button(
                            label="Télécharger Excel",
                            data=output,
                            file_name=f"{project_name.replace(' ', '_')}_tonnage_teneur_krigeage.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"Erreur lors de l'export Excel: {str(e)}")
                        show_detailed_error("Erreur détaillée", e)
        else:
            st.info("🔍 Veuillez d'abord créer et estimer le modèle de blocs pour effectuer l'analyse Tonnage-Teneur.")
else:
    # Page d'accueil avec instructions quand aucun fichier n'est chargé
    st.markdown("""
    ## 👋 Bienvenue dans MineEstim - Outil d'estimation minière par krigeage
    
    Cette application permet d'estimer des ressources minérales en utilisant la méthode du krigeage ordinaire, une technique géostatistique optimale qui prend en compte la structure spatiale de la minéralisation.
    
    ### 🚀 Comment commencer
    
    1. **Chargez un fichier CSV** contenant vos données de forage ou composites depuis le panneau latéral
    2. **Mappez les colonnes** pour identifier les coordonnées X, Y, Z et les teneurs
    3. **Définissez les paramètres** du variogramme et du modèle de blocs
    4. **Créez votre modèle** et lancez l'estimation par krigeage
    
    ### 📊 Fonctionnalités principales
    
    - Modélisation 3D interactive des blocs et composites
    - Analyse statistique complète des données
    - Calculs de tonnage-teneur selon différentes coupures
    - Exportation des résultats en CSV et Excel
    
    ### 🔍 Format de données requis
    
    Votre fichier CSV doit contenir au minimum:
    - Coordonnées X, Y, Z
    - Valeurs de teneur à estimer
    
    Optionnellement:
    - Données de domaine géologique pour le filtrage
    - Valeurs de densité pour des calculs de tonnage précis
    
    Pour commencer, chargez un fichier CSV depuis le panneau de gauche.
    """)
    
    # Afficher un exemple de format de données attendu
    with st.expander("📋 Exemple de format de données"):
        example_data = pd.DataFrame({
            'X': [100, 110, 120, 130, 140],
            'Y': [200, 210, 220, 230, 240],
            'Z': [50, 55, 60, 65, 70],
            'CU_PCT': [0.85, 1.2, 0.76, 0.95, 1.4],
            'DENSITY': [2.65, 2.78, 2.71, 2.69, 2.82],
            'DOMAIN': [1, 1, 1, 2, 2]
        })
        st.dataframe(example_data)
        
        st.markdown("""
        **Notes:**
        - Les noms des colonnes peuvent être différents, vous pourrez les mapper après le chargement
        - Les valeurs numériques peuvent utiliser le point (.) ou la virgule (,) comme séparateur décimal
        - L'application détectera automatiquement les meilleurs paramètres de lecture
        """)