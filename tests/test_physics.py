#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# @file   test_physics.py
# @author Albert Puig (albert.puig@cern.ch)
# @date   27.02.2019
# =============================================================================
"""Test physics output."""

import os
import platform
import subprocess

import pytest

import numpy as np
from scipy.stats import ks_2samp

if platform.system() == 'Darwin':
    import matplotlib

    matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

import uproot

import tensorflow as tf

from tfphasespace import tfphasespace

from plotting import make_norm_histo, mass
import decays
import rapidsim


BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PLOT_DIR = os.path.join(BASE_PATH, 'tests', 'plots')


def create_ref_histos(n_pions):
    """Load reference histogram data."""
    ref_dir = os.path.join(BASE_PATH, 'data')
    if not os.path.exists(ref_dir):
        os.mkdir(ref_dir)
    ref_file = os.path.join(ref_dir, 'bto{}pi.root'.format(n_pions))
    if not os.path.exists(ref_file):
        script = os.path.join(BASE_PATH,
                              'scripts',
                              'prepare_test_samples.cxx+({})'
                              .format(','.join(['"{}"'.format(os.path.join(BASE_PATH,
                                                                           'data',
                                                                           'bto{}pi.root'.format(i + 1)))
                                                for i in range(1, 4)])))
        subprocess.call("echo $PATH", shell=True)
        subprocess.call("root -qb '{}'".format(script), shell=True)
    events = uproot.open(ref_file)['events']
    pion_names = ['pion_{}'.format(pion + 1) for pion in range(n_pions)]
    pions = {pion_name: events.array(pion_name)
             for pion_name in pion_names}
    weights = events.array('weight')
    return [make_norm_histo(array,
                            range_=(-3000 if coord % 4 != 3 else 0, 3000),
                            weights=weights)
            for pion in pions.values()
            for coord, array in enumerate([pion.x, pion.y, pion.z, pion.E])], \
        make_norm_histo(weights, range_=(0, 1))


def run_test(n_particles, test_prefix):
    with tf.Session() as sess:
        weights, particles = sess.run(tfphasespace.generate(decays.B0_AT_REST,
                                                            [decays.PION_MASS] * n_particles,
                                                            100000))
    parts = np.concatenate(particles, axis=0)
    histos = [make_norm_histo(parts[coord],
                              range_=(-3000 if coord % 4 != 3 else 0, 3000),
                              weights=weights)
              for coord in range(parts.shape[0])]
    weight_histos = make_norm_histo(weights, range_=(0, 1))
    ref_histos, ref_weights = create_ref_histos(n_particles)
    p_values = np.array([ks_2samp(histos[coord], ref_histos[coord])[1]
                         for coord, _ in enumerate(histos)] +
                        [ks_2samp(weight_histos, ref_weights)[1]])
    # Let's plot
    x = np.linspace(-3000, 3000, 100)
    e = np.linspace(0, 3000, 100)
    if not os.path.exists(PLOT_DIR):
        os.mkdir(PLOT_DIR)
    for coord, _ in enumerate(histos):
        plt.hist(x if coord % 4 != 3 else e, weights=histos[coord], alpha=0.5, label='tfphasespace', bins=100)
        plt.hist(x if coord % 4 != 3 else e, weights=ref_histos[coord], alpha=0.5, label='TGenPhasespace', bins=100)
        plt.legend(loc='upper right')
        plt.savefig(os.path.join(PLOT_DIR,
                                 "{}_pion_{}_{}.png".format(test_prefix,
                                                            int(coord / 4) + 1,
                                                            ['px', 'py', 'pz', 'e'][coord % 4])))
        plt.clf()
    plt.hist(np.linspace(0, 1, 100), weights=weight_histos, alpha=0.5, label='tfphasespace', bins=100)
    plt.hist(np.linspace(0, 1, 100), weights=ref_weights, alpha=0.5, label='tfphasespace', bins=100)
    plt.savefig(os.path.join(PLOT_DIR, '{}_weights.png'.format(test_prefix)))
    plt.clf()
    assert np.all(p_values > 0.05)


@pytest.mark.flaky(3)  # Stats are limited
def test_two_body():
    """Test B->pipi decay."""
    run_test(2, "two_body")


@pytest.mark.flaky(3)  # Stats are limited
def test_three_body():
    """Test B -> pi pi pi decay."""
    run_test(3, "three_body")


@pytest.mark.flaky(3)  # Stats are limited
def test_four_body():
    """Test B -> pi pi pi pi decay."""
    run_test(4, "four_body")


def run_kstargamma(input_file, kstar_width, b_at_rest, suffix):
    n_events = 1000000
    if b_at_rest:
        input_bs = decays.B0_AT_REST
        rapidsim_getter = rapidsim.get_tree_in_b_rest_frame
    else:
        input_bs = rapidsim.generate_fonll(decays.B0_MASS, 7, 'b', n_events)
        rapidsim_getter = rapidsim.get_tree
    with tf.Session() as sess:
        norm_weights, particles = sess.run(decays.b0_to_kstar_gamma(n_events, kstar_width=kstar_width).generate(input_bs, n_events))
    rapidsim_parts = rapidsim_getter(os.path.join(BASE_PATH,
                                                  'data',
                                                  input_file),
                                     'B0_0',
                                     ('Kst0_0', 'gamma_0', 'Kp_0', 'pim_0'))
    name_matching = {'Kst0_0': 'K*0',
                     'gamma_0': 'gamma',
                     'Kp_0': 'K+',
                     'pim_0': 'pi-'}
    if not os.path.exists(PLOT_DIR):
        os.mkdir(PLOT_DIR)
    x = np.linspace(-3000, 3000, 100)
    e = np.linspace(0, 3000, 100)
    p_values = {}
    for ref_name, ref_part in rapidsim_parts.items():
        tf_part = name_matching[ref_name]
        for coord, coord_name in enumerate(('px', 'py', 'pz', 'e')):
            range_ = (-3000 if coord % 4 != 3 else 0, 3000)
            ref_histo = make_norm_histo(ref_part[coord], range_=range_)
            tf_histo = make_norm_histo(particles[tf_part][coord], range_=range_, weights=norm_weights)
            plt.hist(x if coord % 4 != 3 else e, weights=tf_histo, alpha=0.5, label='tfphasespace', bins=100)
            plt.hist(x if coord % 4 != 3 else e, weights=ref_histo, alpha=0.5, label='RapidSim', bins=100)
            plt.legend(loc='upper right')
            plt.savefig(os.path.join(PLOT_DIR,
                                     "B0_Kstar_gamma_Kstar{}_{}_{}.png".format(suffix, tf_part, coord_name)))
            plt.clf()
            p_values[(tf_part, coord_name)] = ks_2samp(tf_histo, ref_histo)[1]
    plt.hist(np.linspace(0, 1, 100), weights=make_norm_histo(norm_weights, range_=(0, 1)), bins=100)
    plt.savefig(os.path.join(PLOT_DIR, 'B0_Kstar_gamma_Kstar{}_weights.png'.format(suffix)))
    plt.clf()
    return np.array(list(p_values.values()))



@pytest.mark.flaky(3)  # Stats are limited
def test_kstargamma_kstarnonresonant_at_rest():
    """Test B0 -> K* gamma physics with fixed mass for K*."""
    p_values = run_kstargamma('B2KstGamma_RapidSim_7TeV_KstarNonResonant_Tree.root',
                              True, 0, 'NonResonant')
    assert np.all(p_values > 0.05)


@pytest.mark.flaky(3)  # Stats are limited
def test_kstargamma_kstarnonresonant_lhcb():
    """Test B0 -> K* gamma physics with fixed mass for K*."""
    p_values = run_kstargamma('B2KstGamma_RapidSim_7TeV_KstarNonResonant_Tree.root',
                              True, 0, 'NonResonant_LHCb')
    assert np.all(p_values > 0.05)


def test_kstargamma_resonant_at_rest():
    """Test B0 -> K* gamma physics with Gaussian mass for K*.

    Since we don't have BW and we model the resonances with Gaussians,
    we can't really perform the Kolmogorov test wrt to RapidSim,
    so plots are generated and can be inspected by the user. However, small differences
    are expected in the tails of the energy distributions of the kaon and the pion.

    """
    run_kstargamma('B2KstGamma_RapidSim_7TeV_Tree.root',
                   decays.KSTARZ_WIDTH, 'Gaussian')

# def test_kstargamma_lhcb():
#     """Test B0 -> K* gamma physics with boosted B."""
#     # Get our sample
#     with tf.Session() as sess:
#         norm_weights, particles = sess.run(
#             decays.b0_to_kstar_gamma().generate(
#                 rapidsim.generate_fonll(decays.B_MASS, 7, 'b', 1000)))
#     # Get Rapidsim histos
#     ref_histos = rapidsim.load_generated_histos(os.path.join(BASE_PATH,
#                                                              'data',
#                                                              'B2KstGamma_RapidSim_7TeV_KstarStable.root'),
#                                                 ('Kst0_0', 'gamma_0', 'Kp_0', 'pim_0'))
#     name_matching = {'Kst0_0': 'K*0', 'gamma_0': 'gamma', 'Kp_0': 'K+', 'pim_0': 'pi-'}
#     if not os.path.exists(PLOT_DIR):
#         os.mkdir(PLOT_DIR)
#     for particle, ref_histos in ref_histos.items():
#         tf_part = name_matching[particle]
#         for coord, coord_name in enumerate(('px', 'py', 'pz', 'e')):
#             ref_histo = ref_histos[coord]
#             x = (ref_histos[coord].bins[:, 1] + ref_histos[coord].bins[:, 0]) / 2 * 1000.0  # Rapidsim works in GeV
#             tf_histo = make_norm_histo(particles[tf_part][coord], range_=(x[0], x[-1]), weights=norm_weights)
#             ref_histo_norm = ref_histo.values/np.sum(ref_histo.values)
#             plt.hist(x, weights=tf_histo, alpha=0.5, label='tfphasespace', bins=100)
#             plt.hist(x, weights=ref_histo_norm, alpha=0.5, label='RapidSim', bins=100)
#             plt.legend(loc='upper right')
#             plt.savefig(os.path.join(PLOT_DIR,
#                                      "LHCb_B0_Kstar_gamma_Kstar_{}_{}.png".format(tf_part, coord_name)))
#             plt.clf()
#     plt.hist(np.linspace(0, 1, 100), weights=make_norm_histo(norm_weights, range_=(0, 1)))
#     plt.savefig(os.path.join(PLOT_DIR, 'LHCb_B0_Kstar_gamma_Kstar_weights.png'))
#     plt.clf()


def run_k1_gamma(input_file, k1_width, kstar_width, suffix):
    n_events = 1000000
    with tf.Session() as sess:
        norm_weights, particles = sess.run(
            decays.bp_to_k1_kstar_pi_gamma(n_events, k1_width=k1_width, kstar_width=kstar_width)
            .generate(decays.B0_AT_REST, n_events))
    rapidsim_parts = rapidsim.get_tree_in_b_rest_frame(
        os.path.join(BASE_PATH,
                     'data',
                     input_file),
        'Bp_0',
        ('K1_1270_p_0', 'Kst0_0', 'gamma_0', 'Kp_0', 'pim_0', 'pip_0'))
    name_matching = {'K1_1270_p_0': 'K1+',
                     'Kst0_0': 'K*0',
                     'gamma_0': 'gamma',
                     'Kp_0': 'K+',
                     'pim_0': 'pi-',
                     'pip_0': 'pi+'}
    if not os.path.exists(PLOT_DIR):
        os.mkdir(PLOT_DIR)
    x = np.linspace(-3000, 3000, 100)
    e = np.linspace(0, 3000, 100)
    p_values = {}
    for ref_name, ref_part in rapidsim_parts.items():
        tf_part = name_matching[ref_name]
        for coord, coord_name in enumerate(('px', 'py', 'pz', 'e')):
            range_ = (-3000 if coord % 4 != 3 else 0, 3000)
            ref_histo = make_norm_histo(ref_part[coord], range_=range_)
            tf_histo = make_norm_histo(particles[tf_part][coord], range_=range_, weights=norm_weights)
            plt.hist(x if coord % 4 != 3 else e, weights=tf_histo, alpha=0.5, label='tfphasespace', bins=100)
            plt.hist(x if coord % 4 != 3 else e, weights=ref_histo, alpha=0.5, label='RapidSim', bins=100)
            plt.legend(loc='upper right')
            plt.savefig(os.path.join(PLOT_DIR,
                                     "Bp_K1_gamma_K1Kstar{}_{}_{}.png".format(suffix, tf_part, coord_name)))
            plt.clf()
            p_values[(tf_part, coord_name)] = ks_2samp(tf_histo, ref_histo)[1]
    plt.hist(np.linspace(0, 1, 100), weights=make_norm_histo(norm_weights, range_=(0, 1)), bins=100)
    plt.savefig(os.path.join(PLOT_DIR, 'Bp_K1_gamma_K1Kstar{}_weights.png'.format(suffix)))
    plt.clf()
    return np.array(list(p_values.values()))


@pytest.mark.flaky(3)  # Stats are limited
def test_k1gamma_kstarnonresonant_at_rest():
    """Test B0 -> K1 (->K*pi) gamma physics with fixed-mass resonances."""
    p_values = run_k1_gamma('B2K1Gamma_RapidSim_7TeV_K1KstarNonResonant_Tree.root',
                            0, 0, 'NonResonant')
    assert np.all(p_values > 0.05)


def test_k1gamma_resonant_at_rest():
    """Test B0 -> K1 (->K*pi) gamma physics.

    Since we don't have BW and we model the resonances with Gaussians,
    we can't really perform the Kolmogorov test wrt to RapidSim,
    so plots are generated and can be inspected by the user.

    """
    run_k1_gamma('B2K1Gamma_RapidSim_7TeV_Tree.root',
                 decays.K1_WIDTH, decays.KSTARZ_WIDTH, 'Gaussian')


if __name__ == "__main__":
    # test_two_body()
    # test_three_body()
    # test_four_body()
    # test_kstargamma_kstarnonresonant_at_rest()
    # test_kstargamma_resonant_at_rest()
    # test_k1gamma_kstarnonresonant_at_rest()
    # test_k1gamma_resonant_at_rest()
    test_kstargamma_kstarnonresonant_lhcb()

# EOF
