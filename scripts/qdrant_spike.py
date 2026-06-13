"""Qdrant spike: FEN similarity search using TF-IDF (no torch needed)."""
import sqlite3, json, sys, time
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

DB_PATH = '/root/.local/share/chess-coach/sqlite/chess_coach.db'
COLLECTION_NAME = 'chess_positions_spike'
TOP_K = 5

PIECE_VALUES = {'P': 1, 'N': 3, 'B': 3, 'R': 5, 'Q': 9, 'K': 0,
                'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 0}

def fen_to_description(fen: str) -> str:
    """Convert FEN to a rich chess description for embedding."""
    parts = fen.split()
    board = parts[0]
    side = parts[1]
    castling = parts[2] if len(parts) > 2 else '-'
    ep = parts[3] if len(parts) > 3 else '-'
    
    rows = board.split('/')
    
    # Count material from FEN board characters directly
    white_material = 0
    black_material = 0
    white_pawns = black_pawns = 0
    white_knights = black_knights = 0
    white_bishops = black_bishops = 0
    white_rooks = black_rooks = 0
    white_queens = black_queens = 0
    white_king_pos = black_king_pos = None
    total_pieces = 0
    
    for rank_idx, row in enumerate(rows):
        rank = 8 - rank_idx
        file_idx = 0
        for ch in row:
            if ch.isdigit():
                file_idx += int(ch)
            else:
                col = chr(ord('a') + file_idx)
                pos = f"{col}{rank}"
                if ch.isupper():
                    if ch == 'K': white_king_pos = pos
                    elif ch == 'Q': white_queens += 1
                    elif ch == 'R': white_rooks += 1
                    elif ch == 'B': white_bishops += 1
                    elif ch == 'N': white_knights += 1
                    elif ch == 'P': white_pawns += 1
                    white_material += PIECE_VALUES[ch]
                else:
                    if ch == 'k': black_king_pos = pos
                    elif ch == 'q': black_queens += 1
                    elif ch == 'r': black_rooks += 1
                    elif ch == 'b': black_bishops += 1
                    elif ch == 'n': black_knights += 1
                    elif ch == 'p': black_pawns += 1
                    black_material += PIECE_VALUES[ch]
                total_pieces += 1
                file_idx += 1
    
    total_material = white_material + black_material
    
    desc_parts = []
    
    # Phase detection
    num_major = white_queens + black_queens + white_rooks + black_rooks
    
    if total_material < 12 or total_pieces < 10:
        desc_parts.append("endgame")
        if total_material < 6:
            desc_parts.append("minor-piece-endgame")
        if white_pawns == 0 and black_pawns == 0:
            desc_parts.append("pawnless-endgame")
    elif num_major >= 4 or white_queens + black_queens >= 2:
        desc_parts.append("middlegame")
        desc_parts.append("heavy-piece-middlegame")
    else:
        desc_parts.append("opening")
        if total_pieces >= 28:
            desc_parts.append("early-opening")
    
    desc_parts.append(f"{side}-to-move")
    
    # Material balance
    mat_diff = white_material - black_material
    if mat_diff > 3:
        desc_parts.append("white-major-material-advantage")
    elif mat_diff > 0:
        desc_parts.append("white-slight-material-advantage")
    elif mat_diff < -3:
        desc_parts.append("black-major-material-advantage")
    elif mat_diff < 0:
        desc_parts.append("black-slight-material-advantage")
    else:
        desc_parts.append("equal-material")
    
    desc_parts.append(f"white-material-{white_material}")
    desc_parts.append(f"black-material-{black_material}")
    
    # King safety
    if white_king_pos:
        desc_parts.append(f"white-king-{white_king_pos}")
        if white_king_pos in ['g1', 'h1', 'g2', 'h2']:
            desc_parts.append("white-king-kingside-castled")
        elif white_king_pos in ['c1', 'b1', 'c2', 'b2']:
            desc_parts.append("white-king-queenside-castled")
    if black_king_pos:
        desc_parts.append(f"black-king-{black_king_pos}")
        if black_king_pos in ['g8', 'h8', 'g7', 'h7']:
            desc_parts.append("black-king-kingside-castled")
        elif black_king_pos in ['c8', 'b8', 'c7', 'b7']:
            desc_parts.append("black-king-queenside-castled")
    
    # Piece counts
    desc_parts.append(f"white-queens-{white_queens}")
    desc_parts.append(f"black-queens-{black_queens}")
    desc_parts.append(f"white-rooks-{white_rooks}")
    desc_parts.append(f"black-rooks-{black_rooks}")
    desc_parts.append(f"white-knights-{white_knights}")
    desc_parts.append(f"black-knights-{black_knights}")
    desc_parts.append(f"white-bishops-{white_bishops}")
    desc_parts.append(f"black-bishops-{black_bishops}")
    desc_parts.append(f"white-pawns-{white_pawns}")
    desc_parts.append(f"black-pawns-{black_pawns}")
    
    # Pawn structure
    if white_pawns >= 5:
        desc_parts.append("white-heavy-pawn-structure")
    elif white_pawns <= 2:
        desc_parts.append("white-depleted-pawns")
    if black_pawns >= 5:
        desc_parts.append("black-heavy-pawn-structure")
    elif black_pawns <= 2:
        desc_parts.append("black-depleted-pawns")
    
    # Castling rights
    if 'K' in castling: desc_parts.append("white-can-castle-kingside")
    if 'Q' in castling: desc_parts.append("white-can-castle-queenside")
    if 'k' in castling: desc_parts.append("black-can-castle-kingside")
    if 'q' in castling: desc_parts.append("black-can-castle-queenside")
    
    return " ".join(desc_parts)

print("=" * 70)
print("QDANT + TF-IDF SPIKE: Chess Position Similarity Search")
print("=" * 70)

# 1. Connect DB and fetch positions
db = sqlite3.connect(DB_PATH)
cursor = db.cursor()

print(f"\n1. Loading positions from SQLite DB...")
rows = cursor.execute('''
    SELECT id, fen, ply FROM positions 
    WHERE ply BETWEEN 4 AND 30 
    ORDER BY RANDOM() LIMIT 1000
''').fetchall()
print(f"   Loaded {len(rows)} positions")

# 2. Convert FEN to rich descriptions
print(f"\n2. Converting FEN to text descriptions...")
descriptions = []
fen_list = []
for pid, fen, ply in rows:
    desc = fen_to_description(fen)
    descriptions.append(desc)
    fen_list.append(fen)

print(f"   Generated {len(descriptions)} descriptions")
print(f"   Sample description:")
sample_fen = fen_list[0]
print(f"     FEN: {sample_fen}")
print(f"     Desc: {descriptions[0]}")

# Spot-check first query FEN
q1_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
print(f"\n   Query FEN description check:")
print(f"     FEN: {q1_fen}")
print(f"     Desc: {fen_to_description(q1_fen)}")

# 3. TF-IDF vectorization
print(f"\n3. Vectorizing with TF-IDF...")
vectorizer = TfidfVectorizer(max_features=256, analyzer='word', token_pattern=r'\b\w+\b')
vectors = vectorizer.fit_transform(descriptions).toarray()
print(f"   Shape: {vectors.shape}")
print(f"   Vocabulary size: {len(vectorizer.vocabulary_)}")

# 4. Setup Qdrant in-memory
print(f"\n4. Setting up Qdrant in-memory...")
client = QdrantClient(':memory:')

if client.collection_exists(COLLECTION_NAME):
    client.delete_collection(COLLECTION_NAME)

client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=qmodels.VectorParams(
        size=vectors.shape[1],
        distance=qmodels.Distance.COSINE,
    ),
)

# Insert vectors
print(f"   Inserting {len(vectors)} vectors...")
points = []
for i in range(len(vectors)):
    points.append(qmodels.PointStruct(
        id=i,
        vector=vectors[i].tolist(),
        payload={'fen': fen_list[i], 'idx': i, 'desc': descriptions[i]},
    ))
client.upsert(collection_name=COLLECTION_NAME, points=points)
print(f"   Upserted {len(points)} points")

# 5. Test queries
print(f"\n5. Running similarity queries...")
query_fens = [
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",  # King's Pawn (e4)
    "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1",  # Queen's Pawn (d4)
    "4k3/8/8/8/8/8/8/4K3 w - - 0 1",  # Bare kings
    "8/5k2/8/8/8/5K2/8/8 w - - 0 1",  # Two kings
    "3r2k1/pp3ppp/8/2pR4/8/8/PPP2PPP/6K1 w - - 0 1",  # Rook endgame
]

for qidx, qfen in enumerate(query_fens):
    print(f"\n   Query {qidx+1}: {qfen[:60]}...")
    qdesc = fen_to_description(qfen)
    print(f"     Description: {qdesc}")
    
    # Vectorize query
    qvec = vectorizer.transform([qdesc]).toarray()[0]
    
    # Search via Qdrant (use query_points API for newer client)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=qvec.tolist(),
        limit=TOP_K,
        with_payload=True,
    )
    
    print(f"     Top {TOP_K} results:")
    for r in results.points:
        fen = r.payload['fen']
        score = r.score
        print(f"       [{score:.4f}] {fen[:70]}")

print(f"\n{'=' * 70}")
print("Spike complete.")
print(f"{'=' * 70}")
# TODO: try center-weighted FEN text format for better opening discrimination
