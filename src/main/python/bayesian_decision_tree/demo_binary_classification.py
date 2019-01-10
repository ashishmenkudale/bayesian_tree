from bayesian_decision_tree import *
from demo_helper import *
from sklearn.metrics import mean_squared_error


# demo script for binary classification
if __name__ == '__main__':
    proxies = {
        'http': 'SET_HTTP_PROXY',
        'https': 'SET_HTTPS_PROXY'
    }

    color0 = 'b'
    color1 = 'r'

    # binary classification: Beta prior
    prior = (1, 1)

    # Bayesian tree parameters
    partition_prior = 0.9
    delta = 0

    root = BinaryClassificationNode('root', partition_prior, prior, prior, 0)

    # training/test data
    train, test = load_ripley(proxies)

    # train
    data = train[:, :-1]
    target = train[:, -1]
    root.train(data, target, delta)
    print(root)
    print()

    # compute accuracy
    prediction_train = root.predict(train[:, :-1])
    prediction_test = root.predict(test[:, :-1])
    accuracy_train = (0+(prediction_train == train[:, -1])).mean()
    accuracy_test = (0+(prediction_test == test[:, -1])).mean()
    info_train = 'Train accuracy: {} %'.format(100 * accuracy_train)
    info_test = 'Test accuracy:  {} %'.format(100 * accuracy_test)
    print(info_train)
    print(info_test)

    # plot if 1D or 2D
    dimensions = train.shape[1]-1
    if dimensions == 1:
        plot_1d(root, train, info_train, test, info_test)
    elif dimensions == 2:
        plot_2d(root, train, info_train, test, info_test, color0, color1)
