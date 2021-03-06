import numpy as np
from abc import ABC, abstractmethod

class ActivationFunction(ABC):
    def __init__(self):
        pass

    def __call__(self, x):
        return self.forward(x)

    @abstractmethod
    def forward(self, x):
        """
        Given a vectorial/matricial input x,
        compute the forward pass of x through the function, elemtntwise
        Returns a numpy.ndarray with the shape of x
        """
        raise NotImplementedError("ActivationFunction.forward not implemented")

    @abstractmethod
    def backward(self, x):
        """
        Computes the derivative of the function w.r.t. the values in x, 
            elementwise
        Returns a numpy.ndarray with the shape of x
        """
        raise NotImplementedError("ActivationFunction.backward not implemented")

class Identity(ActivationFunction):
    def __init__(self):
        super(Identity, self).__init__()

    def forward(self, x):
        return np.array(x)
    
    def backward(self, x):
        return np.ones(x.shape)

class LeakyReLU(ActivationFunction):
    def __init__(self, neg_slope=0.1):
        super(LeakyReLU, self).__init__()
        self.slope = 0.1

    def forward(self, x):
        out = np.array(x)
        mask = x < 0
        out[mask] = self.slope * x[mask]
        return out

    def backward(self, x):
        out = np.ones(x.shape)
        out[x < 0] = self.slope
        return out

class ReLU(LeakyReLU):
    def __init__(self):
        super(ReLU, self).__init__(0)

class Sigmoid(ActivationFunction):
    def __init__(self):
        super(Sigmoid, self).__init__()

    def forward(self, x):
        return 1 / (1 + np.exp(-x))

    def backward(self, x):
        forward = self.forward(x)
        return forward*(1 - forward)

class LossFunction(ABC):
    def __init__(self):
        pass

    def __call__(self, output, expected):
        return self.loss(output, expected)

    @abstractmethod
    def loss(self, output, expected):
        """
        Given the output of the neural network and the target outcome,
            compute and return the loss (a float)
        Note that the shape of `expected` might depend on the function itself.
        """
        raise NotImplementedError("LossFunction.loss not implemented")

    @abstractmethod
    def backward(self, output, expected):
        """
        Given the output of the neural network and the target outcome,
        compute and return the derivative of the loss function wrt the output.
        Note that the shape of `expected` might depend on the function itself.
        The return value should have the same shape as the `output` arg
        """
        raise NotImplementedError("LossFunction.loss not implemented")

class MSE(LossFunction):
    """
    Implement the MSE loss function, as per
    https://pytorch.org/docs/stable/nn.html#mseloss
    """
    def __init__(self):
        super(MSE, self).__init__()

    def loss(self, output, expected):
        """
        Computes the mean squared L^2 distance between output and expected
        Both arguments should be vectors of the same shape
        """
        return np.mean((output - expected)**2)

    def backward(self, output, expected):
        """
        Computes the derivative of the mean squared L^2 distance between `output`
            and `expected` with respect to `output`
        """
        return 2*(output - expected)/output.size

class CrossEntropyLoss(LossFunction):
    """
    Implement the CrossEntropyLoss as per
    https://pytorch.org/docs/stable/nn.html#crossentropyloss
    """
    def __init__(self):
        super(CrossEntropyLoss, self).__init__()

    def loss(self, output, expected):
        """
        Computes the cross entropy loss given that the correct class
            is the one indexed by `expected` (an integer).
        Assumes that `output` is a column vector.
        """
        return -output[expected, 0] + np.log(np.sum(np.exp(output)))

    def backward(self, output, expected):
        """
        Computes the derivative of the cross entropy w.r.t. output,
            assuming the correct class is indexed by `expected` (an integer)
        """
        exp = np.exp(output)
        grad = exp / np.sum(exp)
        grad[expected] -= 1
        return grad

class NeuralNetwork(object):
    def __init__(self, sizes, *, nonlinearities=None,
                                loss_function=None, lr=0.01):
        """
        Initializes a fully connected neural network with len(sizes) layers,
            where sizes[0] is the input size, sizes[-1] is the output size and
            all the values in between are sizes of hidden layers.
        Can take an additional argument nonlinearities, either an iterable
            of instantiated ActivationFunction objects of length len(sizes)
            or a single instance of an ActivationFunction, in which case that
            same activation function is used in between every layer
            Defaults to LeakyReLU(0.1)
        Can take an additional argument loss_function, a LossFunction object
            specifying the loss function to be used. Defaults to MSE.
        """
        self._sizes = sizes
        self._depth = len(sizes)
        self._lr = lr

        # we assume inputs will be column vectors
        self._weight_matrices = [
            # variance
            (1/np.sqrt(sizes[idx]*sizes[idx+1])) * \
                # matrices with random entries
                np.random.randn(sizes[idx+1], sizes[idx]) for idx in range(self._depth - 1)
        ]
        self._bias_vectors = [
            # variance
            (1/np.sqrt(sizes[idx]*sizes[idx+1])) * \
                # vector with random entries
                np.random.randn(sizes[idx+1], 1) for idx in range(self._depth - 1)
        ]
        if nonlinearities is None:
            nonlinearities = LeakyReLU(0.1)
        if isinstance(nonlinearities, ActivationFunction):
            self._activation_functions = [
                nonlinearities for idx in range(self._depth - 1)
            ]
        elif hasattr(nonlinearities, "__len__") and \
                                len(nonlinearities) == self._depth - 1:
            self._activation_functions = nonlinearities[::]
        else:
            raise ValueError("Could not understand the ActivationFunctions provided")

        if loss_function is None:
            self._loss_function = MSE()
        elif isinstance(loss_function, LossFunction):
            self._loss_function = loss_function
        else:
            raise ValueError("Could not understand the LossFunction provided")

        # store the intermediate computations to enable computing the gradients
        self._intermediates = []
        # store the gradients to enable batch gradient updates
        self._grads = []
        for W, b in zip(self._weight_matrices, self._bias_vectors):
            self._grads.append((np.zeros(W.shape), np.zeros(b.shape)))
        # store the number of backpasses we already did, so we can average
        self._passes_done = 0

    def forward(self, x):
        """
        Given a (column) vector x, performs a forward pass with the given
        vector; returns the result of the forward pass.
        """
        x = np.array(x)
        if len(x.shape) == 1:
            x = np.expand_dims(x, -1)
        elif len(x.shape) == 2:
            if x.shape[0] != self._sizes[0] and x.shape[1] == self._sizes[0]:
                x = x.T
            else:
                ValueError("Unexpected input of shape {}".format(x.shape))
        else:
            ValueError("Input has too many dimensions ({})".format(len(x.shape)))

        self._intermediates = [(None, x[::, ::])]
        acc = x
        for mat, bias, nonlin in zip(self._weight_matrices, self._bias_vectors,
                                        self._activation_functions):
            pre_nonlin = np.dot(mat, acc) + bias
            ## apply leaky-ReLU non-linearity
            post_nonlin = nonlin(pre_nonlin)
            self._intermediates.append((pre_nonlin, post_nonlin))
            acc = post_nonlin
        return acc

    def loss(self, output):
        """
        Taken a (column) vector with the expected result, compute
        the mean squared error with respect to the last forward pass.
        Also stores the gradients induced by the expected outcome.
        Returns 1/2(sum((y_hat - y)^2))
        """
        out = np.array(output)
        if len(out.shape) == 1:
            out = np.expand_dims(out, -1)
        elif len(out.shape) == 2:
            if out.shape[0] != self._sizes[0] and out.shape[1] == self._sizes[0]:
                out = out.T
            else:
                ValueError("Unexpected input of shape {}".format(out.shape))
        else:
            ValueError("Input has too many dimensions ({})".format(len(out.shape)))
        net_outs = self._intermediates[-1][-1]
        loss = self._loss_function(net_outs, output)

        # compute the gradients in a backward fassion
        self._passes_done += 1
        for t in range(self._depth - 2, -1, -1):
            # row vector
            if t + 1 == self._depth - 1:
                dLdpos = self._loss_function.backward(net_outs, output).T # row
            else:
                Wfront = self._weight_matrices[t+1] # matrix
                dLdpos = np.dot((dLdpos*dfdpre.T), Wfront)
            pos = self._intermediates[t][1] # column
            preFront = self._intermediates[t+1][0] # column
            act = self._activation_functions[t]
            dfdpre = act.backward(preFront)
            dposdW = np.dot(dfdpre, pos.T)
            dLdW = dLdpos.T*dposdW
            dLdb = dfdpre*dLdpos.T
            # accumulate
            prevW, prevb = self._grads[t]
            self._grads[t] = (prevW + dLdW, prevb + dLdb)

        return loss

    def backprop(self, learning_rate=None):
        """
        Alters the weights and biases with the gradients stored
        """
        lr = self._lr if learning_rate is None else learning_rate
        for i in range(self._depth - 1):
            self._weight_matrices[i] -= lr*self._grads[i][0]/self._passes_done
            self._bias_vectors[i] -= lr*self._grads[i][1]/self._passes_done
            self._grads[i] = (np.zeros(self._grads[i][0].shape),
                                np.zeros(self._grads[i][1].shape))
        self._passes_done = 0

if __name__ == "__main__":
    import matplotlib.pyplot as plt

    #nn = NeuralNetwork((3,4,2), nonlinearities=LeakyReLU(0.1))
    #nn = NeuralNetwork((3,4,2), nonlinearities=Identity())
    #nn = NeuralNetwork((3,4,2), nonlinearities=Sigmoid())
    nn = NeuralNetwork((3,4,2), nonlinearities=ReLU())
    losses = []
    for _ in range(3000):
        for _ in range(20):
            nn.forward(np.random.rand(3,1))
            nn.loss(np.ones((2,1)))
        nn.forward(np.random.rand(3,1))
        losses.append(nn.loss(np.ones((2,1))))
        nn.backprop()
    print(nn.forward(np.random.rand(3,1)))
    plt.plot(losses)
    plt.show()