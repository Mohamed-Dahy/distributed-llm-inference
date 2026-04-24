from rag.retriever import retrieve_context

queries = [
    "what is supervised learning and how does it work",
    "explain the gradient descent optimization algorithm",
    "what is overfitting and how do you prevent it",
    "how does a neural network learn from training data",
    "what is the bias variance tradeoff in machine learning",
]

print("=" * 60)
for q in queries:
    result = retrieve_context(q)
    print(f"\nQuery:   {q}")
    print(f"Context: {result[:120]}...")
print("=" * 60)
