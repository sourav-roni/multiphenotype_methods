import numpy as np
from multiphenotype_utils import (get_continuous_features_as_matrix, add_id, remove_id_and_get_mat, 
    partition_dataframe_into_binary_and_continuous, divide_idxs_into_batches)
import pandas as pd
import tensorflow as tf
from dimreducer import DimReducer

from general_autoencoder import GeneralAutoencoder
from standard_autoencoder import StandardAutoencoder
from variational_autoencoder import VariationalAutoencoder



import tensorflow.compat.v1 as tf
tf.disable_v2_behavior() 

class VariationalLaplacianAutoencoder(VariationalAutoencoder):
    """
    Implements a variational autoencoder with independent Laplacian priors. 
    This code is identical to the Gaussian variational except where explicitly noted in comments. 
    """    
    def __init__(self, 
                 **kwargs):
        super(VariationalLaplacianAutoencoder, self).__init__(**kwargs)   
        
    def encode(self, X):          
        num_layers = len(self.encoder_layer_sizes)
        # Get mu 
        mu = X
        for idx in range(num_layers):
            mu = tf.matmul(mu, self.weights['encoder_h%i' % (idx)]) \
                + self.biases['encoder_b%i' % (idx)]
            # No non-linearity on the last layer
            if idx != num_layers - 1:
                mu = self.non_linearity(mu)
        Z_mu = mu

        # Get sigma (often called b, but we call it sigma to avoid renaming everything). 
        sigma = X
        for idx in range(num_layers):
            sigma = tf.matmul(sigma, self.weights['encoder_h%i_sigma' % (idx)]) \
                + self.biases['encoder_b%i_sigma' % (idx)]
            # No non-linearity on the last layer
            if idx != num_layers - 1:
                sigma = self.non_linearity(sigma)
        sigma = sigma * self.sigma_scaling # scale so sigma doesn't explode when we exponentiate it. 
        sigma = tf.exp(sigma)
        Z_sigma = sigma
        # Important: this deviates from the standard Gaussian autoencoder
        # Sample from Laplacian(mu, sigma). 
        # See https://en.wikipedia.org/wiki/Laplace_distribution#Generating_random_variables_according_to_the_Laplace_distribution
        # Z = mu - b * sgn(eps) * ln(1 - 2|eps|) where eps ~ U(-.5, .5)
        # add in small constant (1e-8) for numerical stability in sampling; otherwise log can explode. 

        eps = tf.random_uniform(tf.shape(Z_mu), 
                                     dtype=tf.float32, 
                                     minval=-.5, 
                                     maxval=.5,
                                     seed=self.random_seed)
        Z = Z_mu - Z_sigma * tf.sign(eps) * tf.log(1 - 2 * tf.abs(eps) + 1e-8) 
        return Z, Z_mu, Z_sigma

    def set_up_regularization_loss_structure(self):
        """
        This function sets up the basic loss structure. Should define self.reg_loss. 
        """
        self.reg_loss = self.get_regularization_loss(self.Z_mu, self.Z_sigma)
    
    def get_regularization_loss(self, Z_mu, Z_sigma):
        # Important: this deviates from the standard Gaussian autoencoder
        # We assume that the prior is a Laplacian with sigma = 1, mu = 0.
        # to compute q log p: https://www.wolframalpha.com/input/?i=integrate++1+%2F+(2+*+pi)+*+exp(-abs(x+-+7)+%2F+pi)+*+(-abs(x)+%2F+1)+from+-infinity+to+infinity
        # to compute q log q: https://www.wolframalpha.com/input/?i=integrate++1+%2F+(2+*+pi)+*+exp(-abs(x+-+7)+%2F+pi)+*+(-abs(x+-+7)+%2F+pi)+from+-infinity+to+infinity
        # We want to compute KL(Q, P) and we have 
        # mu_p = 0, sigma_p = 1. Then: 
        # KL(Q, P) = -log(sigma) - 1 - (- abs(mu) - sigma * exp(-abs(mu) / sigma))
        # KL(Q, P) = -log(sigma) - 1 + abs(mu) + sigma * exp(-abs(mu) / sigma)
        # which vanishes, as it should, when sigma = 1, mu = 0. 
        
        kl_div_loss = -tf.log(Z_sigma) - 1 + tf.abs(Z_mu) + Z_sigma * tf.exp(-tf.abs(Z_mu) / Z_sigma)
        kl_div_loss = tf.reduce_mean(
            tf.reduce_sum(
                kl_div_loss,
                axis=1),
            axis=0)
        return kl_div_loss
