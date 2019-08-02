#!/usr/bin/env python3

###############################################################################
# Program: TransmissionCluster.py
# Type: Python Script
# Version: 1.0
# Author: Steven J. Clipman
# Description: Efficient distance-free method for defining clusters from phylogenetic trees
# License: MIT
###############################################################################

from queue import Queue
from treeswift import read_tree_newick
import PySimpleGUI as sg
import os
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import math
import statistics


NUM_THRESH = 1000  # number of thresholds to calculate genetic distance over


# cut out the current node's subtree (by setting all nodes' DELETED to True) and return list of leaves
def cut(node):
    cluster = list()
    descendants = Queue()
    descendants.put(node)
    while not descendants.empty():
        descendant = descendants.get()
        if descendant.DELETED:
            continue
        descendant.DELETED = True
        descendant.left_dist = 0
        descendant.right_dist = 0
        descendant.edge_length = 0
        if descendant.is_leaf():
            cluster.append(str(descendant))
        else:
            for c in descendant.children:
                descendants.put(c)
    return cluster


# initialize properties of input tree and return set containing taxa of leaves
def prep(tree, support):
    tree.resolve_polytomies()
    tree.suppress_unifurcations()
    leaves = set()
    for node in tree.traverse_postorder():
        if node.edge_length is None:
            node.edge_length = 0
        node.DELETED = False
        if node.is_leaf():
            leaves.add(str(node))
        else:
            try:
                node.confidence = float(str(node))
            except:
                node.confidence = 100.  # give edges without support values support 100
            if node.confidence < support:  # don't allow low-support edges
                node.edge_length = float('inf')
    return leaves


# min_clusters_threshold_max, but all clusters must define a clade
def min_clusters_threshold_max_clade(tree, threshold, support):
    leaves = prep(tree, support)
    clusters = list()
    for node in tree.traverse_postorder():
        # if I've already been handled, ignore me
        if node.DELETED:
            continue

        # find my undeleted max distances to leaf
        if node.is_leaf():
            node.left_dist = 0
            node.right_dist = 0
        else:
            children = list(node.children)
            if children[0].DELETED and children[1].DELETED:
                cut(node)
                continue
            if children[0].DELETED:
                node.left_dist = 0
            else:
                node.left_dist = max(children[0].left_dist, children[0].right_dist) + children[0].edge_length
            if children[1].DELETED:
                node.right_dist = 0
            else:
                node.right_dist = max(children[1].left_dist, children[1].right_dist) + children[1].edge_length

            # if my kids are screwing things up, cut both
            if node.left_dist + node.right_dist > threshold:
                cluster_l = cut(children[0])
                node.left_dist = 0
                cluster_r = cut(children[1])
                node.right_dist = 0

                # add cluster
                for cluster in (cluster_l, cluster_r):
                    if len(cluster) != 0:
                        clusters.append(cluster)
                        for leaf in cluster:
                            leaves.remove(leaf)

    # add all remaining leaves to a single cluster
    if len(leaves) != 0:
        clusters.append(list(leaves))
    return clusters


# pick the threshold between 0 and "distance threshold" that maximizes number of (non-singleton) clusters
def argmax_clusters(method, tree, threshold, support, display_fig):
    supportTemp = float('-inf')
    if display_fig is True:
        distfile = open("TransmissionCluster_PlotData_NumClusters_by_DistanceThreshold.txt", 'w')
        distfile.write("Distance\tNumClusters\n")
    from copy import deepcopy
    thresholds = [i*threshold/NUM_THRESH for i in range(NUM_THRESH+1)]
    best = None
    best_num = -1
    best_t = -1
    distv = []
    xs = []
    ys = []
    for i, t in enumerate(thresholds):
        sg.OneLineProgressMeter('TransmissionCluster', i+1, len(thresholds)-1, 'key', 'Computing best genetic distance threshold...', orientation='h')
        clusters = method(deepcopy(tree), t, supportTemp)
        num_non_singleton = len([c for c in clusters if len(c) > 1])
        if display_fig is True:
            distfile.write("%s\t%s\n" % (t, num_non_singleton))
        xs.append(float(t))
        ys.append(int(num_non_singleton))
        if num_non_singleton > best_num:
            best = clusters
            best_num = num_non_singleton
            raw_t = t
            best_t = float(round(t, 3))
    best = method(deepcopy(tree), best_t, support)
    outfile.write("Genetic Distance Uperbound: %s\n" % threshold)
    outfile.write("Best Distance Threshold: %s\n" % best_t)

    if display_fig is True:
        distfile.close()
        plt.figure(2)
        plt.bar(xs, ys, width=0.001)
        plt.ylabel('Number of Clusters')
        plt.xlabel('Genetic Distance Threshold')

    return best


# plot distance histogram
def gen_hist(tree, display_fig):
    if display_fig is True:
        histfile = open("TransmissionCluster_PlotData_Pairwise_Distance_Histogram.txt", 'w')
    pw_dists = []
    distance_matrix = tree.distance_matrix(leaf_labels=True)
    for u in distance_matrix.keys():
        for v in distance_matrix[u].keys():
            pw_dists.append(distance_matrix[u][v])
            if display_fig is True:
                histfile.write("%s\t%s\t%s\n" % (u, v, distance_matrix[u][v]))

    bin_size = int(math.ceil(math.sqrt(len(pw_dists)) / 10.0)) * 10
    plt.figure(1)
    plt.hist(pw_dists, bins=bin_size)
    plt.ylabel('Count')
    plt.xlabel('Sample Pairwise Genetic Distance')
    histarray = plt.hist(pw_dists, bins=bin_size)[0]
    binsarray = plt.hist(pw_dists, bins=bin_size)[1]
    if display_fig is True:
        histfile.close()
    return histarray, binsarray


# get upper limit for computing genetic distance thresholds
def get_dist_limit(hist_plot):
    histarray = hist_plot[0]
    binsarray = hist_plot[1]
    ff = histarray[:5]
    meanff = statistics.mean(ff)
    maxarray = []
    for i in range(5, len(histarray)):
        curSet = histarray[i-5:i]
        if statistics.mean(curSet) < meanff:
            maxarray.append(binsarray[i])

    d = round(float(maxarray[1]), 3)

    return d


# generate edge list to visualize clusters in gephi
def generate_edge_list(tree, cluster_members):
    outname = "TransmissionCluster_Network_Diagram_Edge_List.txt"
    outfile = open(outname, 'w')
    outfile.write("Source\tTarget\n")
    distance_matrix = tree.distance_matrix(leaf_labels=True)
    for cluster_num in cluster_members.keys():
        clustered_samples = cluster_members[cluster_num]
        if len(clustered_samples) == 2:
            outfile.write("%s\t%s\n" % (clustered_samples[0], clustered_samples[1]))
        else:
            for i in range(len(clustered_samples)):
                id1 = clustered_samples[i]
                dist = 1000
                edgeTo = ''
                for j in range(i+1, len(clustered_samples)):
                    id2 = clustered_samples[j]
                    if distance_matrix[id1][id2] < dist:
                        dist = distance_matrix[id1][id2]
                        edgeTo = id2
                if edgeTo != '':
                    outfile.write('%s\t%s\n' % (id1, edgeTo))
    outfile.close()


if __name__ == "__main__":
    # Render GUI window
    passingfile = False
    passingdist = False
    passingsupp = False
    window = ''
    while passingfile is False or passingdist is False or passingsupp is False:
        if window != '':
            window.Close()
        layout = [#[sg.Image(r'resources/logo.png')],
                    [sg.Text("TransmissionCluster", font=('Helvetica', 24, 'bold'))],
                    [sg.Text("Written By: Steven J. Clipman, Johns Hopkins University\n", font=('Helvetica', 14))],
                    [sg.Text('Newick Tree File*:', font=('Helvetica', 13)), sg.InputText(font=('Helvetica 13'), key='infilename'), sg.FileBrowse(font=('Helvetica 13'))],
                    [sg.Text('Output Filename*:', font=('Helvetica', 13)), sg.InputText(font=('Helvetica 13'), default_text='TransmissionCluster_Results.txt', text_color='gray', key='outfilename')],
                    [sg.Text('Genetic Distance Threshold (optional):', font=('Helvetica 13')), sg.InputText(font=('Helvetica 13'), key='dist'), sg.Checkbox('Compute Best Distance Threshold', font=('Helvetica 13'), default=False, key='df')],
                    [sg.Text('Support Threshold (optional):', font=('Helvetica 13')), sg.InputText(font=('Helvetica 13'), key='support')],
                    [sg.Checkbox('Plot Histograms', font=('Helvetica 13'), default=True, key='plothist'), sg.Checkbox('Export Network Edge List', font=('Helvetica 13'), default=False, key='edge')],
                    [sg.OK('Analyze', font=('Helvetica', 13), size=(10, 2))]]

        window = sg.Window('TransmissionCluster', layout)
        event, values = window.Read()

        # parse user arguments
        if os.path.exists(values['infilename']) is not True:
            sg.Popup("Error: Input tree not found.", font=('Helvetica', 13, 'bold'))
            passingfile = False
        else:
            passingfile = True
        try:
            float(values['dist'])
            if float(values['dist']) > 1 or float(values['dist']) < 0:
                sg.Popup("Error: Genetic distance threshold must be between 0 and 1.", font=('Helvetica', 13, 'bold'))
                passingdist = False
            else:
                passingdist = True
        except ValueError:
            if values['df'] is not True:
                sg.Popup("Error: Genetic distance threshold must be between 0 and 1 or 'Compute Best Distance Threshold' must be selected.", font=('Helvetica', 13, 'bold'))
                passingdist = False
            else:
                passingdist = True

        if values['support'] != '':
            try:
                float(values['support'])
                if float(values['support']) > 1 or float(values['support']) < 0:
                    sg.Popup("Error: Support threshold must be between 0 and 1.", font=('Helvetica', 13, 'bold'))
                    passingsupp = False
                else:
                    passingsupp = True
            except ValueError:
                sg.Popup("Error: Support threshold must be between 0 and 1.", font=('Helvetica', 13, 'bold'))
                passingsupp = False
        else:
            passingsupp = True


    infile = open(values['infilename'], 'r')
    outfile = open(values['outfilename'], 'w')
    if values['support'] == '':
        values['support'] = '-inf'
    trees = list()
    for line in infile:
        if isinstance(line, bytes):
            l = line.decode().strip()
        else:
            l = line.strip()
        trees.append(read_tree_newick(l))

    # run algorithm
    outfile.write("** TransmissionCluster Results **\n")
    outfile.write("Input File: %s\n" % values['infilename'])
    outfile.write("Support Threshold: %s\n" % values['support'])
    for t, tree in enumerate(trees):
        # plot pairwise distances
        visable = False
        if values['plothist'] is True:
            visable = True
        if values['df'] is False:
            outfile.write("Genetic Distance Threshold: %s\n" % values['dist'])
            if visable is True:
                gen_hist(tree, visable)
            clusters = min_clusters_threshold_max_clade(tree, float(values['dist']), float(values['support']))
        else:
            histarray = gen_hist(tree, visable)
            d = get_dist_limit(histarray)
            clusters = argmax_clusters(min_clusters_threshold_max_clade, tree, float(d), float(values['support']), visable)
        cluster_num = 1
        clust_members = {}
        for cluster in clusters:
            if len(cluster) > 1:
                for l in cluster:
                    if cluster_num in clust_members:
                        samplenames = clust_members[cluster_num]
                        samplenames.append(l)
                        clust_members[cluster_num] = samplenames
                    else:
                        samplenames = [l]
                        clust_members[cluster_num] = samplenames
                cluster_num += 1
        totalclusters = clust_members
        cluster_num -= 1
        outfile.write('Found %s clusters\n\n' % cluster_num)
        header = "ClusterNum\tNumberOfSamples\tSampleNames\n"
        outfile.write(header)
        total = 0
        for k in clust_members.keys():
            total += len(clust_members[k])
            outfile.write("%s\t%s\t[%s]\n" % (k, len(clust_members[k]), (','.join(clust_members[k]))))
        outfile.write("\n-------------------------------\nTotal Samples Clustered: %s" % total)
    outfile.close()
    if values['edge'] is True:
        generate_edge_list(tree, clust_members)
    sg.PopupOK('Process Complete!',
        'Results have been written to the output file:\n%s' % values['outfilename'],
        'Plots will now be displayed (if option checked)...', font=('Helvetica', 13))

    if visable is True:
        plt.show()
