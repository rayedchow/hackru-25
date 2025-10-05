import numpy as np


def _to_np(emb):
    # emb might be memoryview/bytes/list; normalize to np.float32 2D array
    if isinstance(emb, memoryview):
        emb = emb.tobytes()
    if isinstance(emb, (bytes, bytearray)):
        # not typical; your emb should be an array-like; guard just in case
        raise ValueError("Unexpected binary embedding format")
    return np.asarray(emb, dtype=np.float32)


def l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
    return mat / norms


def pca_3d(vectors: list[list[float]], normalize=True) -> np.ndarray:
    """
    Fast deterministic 3D projection using PCA.
    Returns an N x 3 numpy array.
    """
    X = np.vstack([_to_np(v) for v in vectors])  # (N, D)
    if normalize:
        X = l2_normalize(X)  # cosine-friendly
    Xc = X - X.mean(axis=0, keepdims=True)
    # SVD for PCA
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    # Project onto first 3 PCs
    Z = Xc @ Vt[:3].T  # (N, 3)
    # optional scaling for nicer plotting
    Z = Z / (np.std(Z, axis=0, keepdims=True) + 1e-8)
    return Z.astype(np.float32)


# Optional: UMAP/t-SNE (uncomment if you want)
# pip install umap-learn scikit-learn
def umap_3d(
    vectors: list[list[float]],
    n_neighbors=15,
    min_dist=0.1,
    metric="cosine",
    normalize=True,
    random_state=42,
):
    import umap

    X = np.vstack([_to_np(v) for v in vectors])
    if normalize and metric == "cosine":
        X = l2_normalize(X)
    reducer = umap.UMAP(
        n_components=3,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=random_state,
    )
    Z = reducer.fit_transform(X)
    return Z.astype(np.float32)


def tsne_3d(
    vectors: list[list[float]],
    perplexity=30,
    metric="cosine",
    normalize=True,
    random_state=42,
):
    from sklearn.manifold import TSNE

    X = np.vstack([_to_np(v) for v in vectors])
    if normalize and metric == "cosine":
        X = l2_normalize(X)
    # sklearn TSNE doesn't do cosine natively; use 'cosine' via precomputed or switch to 'euclidean' on normalized data
    Z = TSNE(
        n_components=3,
        perplexity=perplexity,
        learning_rate="auto",
        init="pca",
        random_state=random_state,
        metric="euclidean",
    ).fit_transform(X)
    return Z.astype(np.float32)
