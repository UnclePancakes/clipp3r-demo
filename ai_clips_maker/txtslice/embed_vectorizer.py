"""Embed text using a compact sentence model for topic segmentation."""

import torch
from sentence_transformers import SentenceTransformer


class TextEmbedder:
    """
    Generates sentence embeddings for semantic comparison and segmentation.
    """

    def __init__(self) -> None:
        """
        Initializes the SentenceTransformer model.
        """
        self.__model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed_sentences(self, sentences: list[str]) -> torch.Tensor:
        """
        Transforms a list of sentences into embedding vectors.

        Parameters
        ----------
        sentences: list[str]
            A list of strings, where each string is a sentence.

        Returns
        -------
        torch.Tensor
            A 2D tensor of shape (N x E), where N is the number of sentences
            and E is the embedding dimension.
        """
        embeddings = self.__model.encode(sentences, convert_to_tensor=True)
        return embeddings
