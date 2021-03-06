"""VRNN model that uses both LSTM cell and latent states sampled from a feature extraction
network to generate text."""
from __future__ import division

import tensorflow as tf

from utils import KLGaussianStdGaussian, FullyConnected, VRNNModel

class LatentLSTMVRNNModel(VRNNModel):

    def __init__(self, args):
        self.batch_size = batch_size = args.batch_size
        self.seq_length = seq_length = args.seq_length
        size = args.latent_dimensions
        num_layers = args.num_layers
        vocab_size = args.vocab_size
        
        x_dim = 200
        x2s_dim = 200
        z2s_dim = 200
        p_x_dim = 200

        self._input_data = tf.placeholder(tf.int32, [batch_size, seq_length])
        self._targets = tf.placeholder(tf.int32, [batch_size, seq_length])

        with tf.device('/cpu:0'):
            embedding = tf.get_variable('embedding',
                                        [vocab_size, vocab_size],
                                        dtype=tf.float32)
            inputs = tf.nn.embedding_lookup(embedding, self._input_data)

        inputs = [tf.squeeze(input_step, [1])
                  for input_step in tf.split(1, seq_length, inputs)]

        cell = tf.nn.rnn_cell.LSTMCell(size, state_is_tuple=True)
        cell = tf.nn.rnn_cell.MultiRNNCell([cell] * num_layers, state_is_tuple=True)
        self._initial_state = cell.zero_state(batch_size, tf.float32)
        h, last_state = tf.nn.rnn(cell,
                inputs,
                initial_state=self._initial_state)

        h = tf.reshape(tf.concat(1, h), [-1, size])
        theta_1 = FullyConnected(z,
                [size, p_x_dim],
                unit='relu',
                name='theta_1')

        theta_2 = FullyConnected(theta_1,
                [p_x_dim, p_x_dim],
                unit='relu',
                name='theta_2')

        theta_3 = FullyConnected(theta_2,
                [p_x_dim, p_x_dim],
                unit='relu',
                name='theta_3')

        theta_4 = FullyConnected(theta_3,
                [p_x_dim, p_x_dim],
                unit='linear',
                name='theta_4')

        logits = FullyConnected(theta_4,
                [p_x_dim, vocab_size],
                unit='linear',
                name='logits')
        self._probs = tf.nn.softmax(logits)

        recon_loss = tf.nn.seq2seq.sequence_loss_by_example(
                [logits],
                [tf.reshape(self._targets, [-1])],
                [tf.ones([batch_size * seq_length], dtype=tf.float32)],
                vocab_size)
        kl_loss = [KLGaussianStdGaussian(z_mean, z_log_sigma_sq)
                for _, z_mean, z_log_sigma_sq in last_state]

        self._cost = tf.reduce_mean(kl_loss) \
                + tf.reduce_sum(recon_loss) / batch_size / seq_length

        self._final_state = last_state

        self._lr = tf.Variable(0.0, trainable=False)
        tvars = tf.trainable_variables()
        grads, _ = tf.clip_by_global_norm(tf.gradients(self._cost, tvars),
                                          args.max_grad_norm)
        optimizer = tf.train.AdamOptimizer(self._lr)
        self._train_op = optimizer.apply_gradients(zip(grads, tvars))

        self._new_lr = tf.placeholder(tf.float32, shape=[],
                                      name='new_learning_rate')
        self._lr_update = tf.assign(self._lr, self._new_lr)

