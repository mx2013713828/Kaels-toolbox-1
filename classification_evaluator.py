#!/usr/bin/env python
# -*- coding: utf-8 -*-
# created 2017/05/02 @Northrend
#
# Unified image classification evaluator
# On log generated by Kael's toolbox
#


import os
import sys
import json
import docopt
from AvaLib import _time_it
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot
import seaborn
import pandas
import re
import logging


POSITIVE = 1
RESULT_FILE = 'result'


# init global logger
log_format = '%(asctime)s %(levelname)s: %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger()


def _init_():
    '''
    Evalutaion script for image-classification task
    Update: 2018/02/08
    Author: @Northrend
    Contributor:

    Change log:
    2018/02/08      v2.0            support save error log
    2017/12/05      v1.5            support evaluation on all labels
    2017/08/15      v1.4            support confusion matrix
    2017/07/30      v1.3            support mxnet log
    2017/06/09      v1.2            support online-service log
    2017/06/05      v1.1            fixed AP calculation
                                    support missing files counting
    2017/05/11      v1.0            basic functions

    Usage:
        classification_evaluator.py     <in-log> <out-path> (--gt=str)
                                        [-s|--service -c|--conf-mat -a|--all-labels -e|--err-log]
                                        [--log-lv=str --pos=int --label=str --nrop]
                                        [--top-k=int --label-range=int]
        classification_evaluator.py     -v | --version
        classification_evaluator.py     -h | --help

    Arguments:
        <in-log>                    test inference log
        <out-path>                  evaluation result file

    Options:
        -h --help                   show this help screen
        -v --version                show current version
        -s --service                online-service log mode
        -c --conf-mat               generate confusion matrix mode
        -a --all-labels             recurrently eval on all labels mode
        -e --err-log                save error image json as /out-path/err.json
        ---------------------------------------------------------------------------------------------------
        --log-lv=str                logging level, one of INFO DEBUG WARNING ERROR CRITICAL [default: INFO]
        --gt=str                    groundtruth file list, required argument
        --pos=int                   set positive label index, will be disabled under all-label mode
        --label-range=int           number of labels, will be used under all-label mode
        --nrop                      set nrop flag to convert nrop logs
        --label=str                 path to index2label file
        --top-k=int                 top k in log [default: 1]
    '''
    logger.setLevel(eval('logging.{}'.format(args['--log-lv'])))
    logger.info('=' * 80 + '\nArguments submitted:')
    for key in sorted(args.keys()):
        logger.info('{:<20}= {}'.format(key.replace('--', ''), args[key]))
    logger.info('=' * 80)


def _check_path(path):
    '''
    check path existence
    '''
    if not os.path.exists(path):
        os.mkdir(path)
        logger.info('{} created'.format(path))
    return 0


def _read_list(image_list_file):
    '''
    read groundtruth list
    file syntax:
    /path/to/image1/jpg label_index
    /path/to/image2.jpg label_index
    '''
    dict_gt = dict()
    f_image_list = open(image_list_file, 'r')
    for buff in f_image_list:
        dict_gt[os.path.basename(buff.strip().split()[0])] = int(buff.split()[1])
    return dict_gt


def _read_category(label_list_file, position=1):
    '''
    read "index to label" file
    '''
    lst_label = list()
    f_label_list = open(label_list_file, 'r')
    for buff in f_label_list:
        lst_label.append(buff.strip().split()[position])
    return lst_label


def _is_positive(dict_image, threshold):
    '''
    positive judgement
    '''
    if float(dict_image['Confidence'][POSITIVE]) > threshold:
        return True
    else:
        return False


def _draw_2d_curve(lst_x, lst_y, save_path='./tmp.png', style='--r', xlabel='x', ylabel='y'):
    '''
    draw curves
    '''
    # pyplot.axis([0, 1, 0, 1])
    pyplot.plot(lst_x, lst_y, style, lw=1.5)
    pyplot.grid(True)
    pyplot.xlabel(xlabel)
    pyplot.ylabel(ylabel)
    pyplot.title('{}-{} Curve'.format(ylabel, xlabel))
    pyplot.savefig(save_path)
    pyplot.close()      # release cache, or next picture will get fucked


def _draw_confusion_matrix(dict_log, dict_gt, label_position=1):
    '''
    TODO
    '''
    label_lst = _read_category(args['--label'], position=label_position)
    logger.debug(label_lst)
    matrix = [[0 for col in xrange(len(label_lst))]
              for row in xrange(len(label_lst))]
    # update confusion matrix
    for image in dict_log:
        try:
            if image not in dict_gt:
                logger.error('image not found in groundtruth file')
                # miss += 1
                continue
            elif type(dict_log[image]['Top-{} Index'.format(args['--top-k'])]) == list:
                matrix[dict_log[image]['Top-{} Index'.format(args['--top-k'])][0]][dict_gt[image]] += 1
            elif type(dict_log[image]['Top-{} Index'.format(args['--top-k'])]) == int:
                matrix[dict_log[image]['Top-{} Index'.format(args['--top-k'])]][dict_gt[image]] += 1
        except:
            logger.debug('update matrix error')

    df_cm = pandas.DataFrame(matrix, index=[cls for cls in label_lst], columns=[cls for cls in label_lst])
    logger.debug('start drawing confusion matrix')
    logger.debug(matrix)
    pyplot.figure(figsize=(len(matrix), len(matrix) + 3))
    logger.debug(df_cm)
    try:
        seaborn.heatmap(df_cm, annot=True, cmap='Reds')
        pyplot.savefig('./test.png')
    except:
        logger.warn('drawing matrix failed')
        for row in matrix:
            logger.info(row)
    pyplot.close()


def _calculate_ap(lst_rec, lst_pre):
    '''
    calculate average precision for one class
    '''
    # initialize AP
    AP = lst_rec[-1] * lst_pre[-1]
    for i in xrange(1, len(lst_rec)):
        AP += min(lst_pre[i], lst_pre[i - 1]) * (lst_rec[i - 1] - lst_rec[i])
    return AP


def _calculate_pr(dict_log, dict_gt):
    '''
    calculate precision and recall values according to top-1 index
    '''
    tp = 0
    fp = 0
    fn = 0
    for image in dict_log.keys():
        if image not in dict_gt:    # image check
            continue
        elif dict_log[image]['Top-1 Index'] == POSITIVE and dict_gt[image] == POSITIVE:
            tp += 1
        elif dict_log[image]['Top-1 Index'] == POSITIVE and dict_gt[image] != POSITIVE:
            fp += 1
        elif dict_log[image]['Top-1 Index'] != POSITIVE and dict_gt[image] == POSITIVE:
            fn += 1
    precision, recall = (float(tp) / (tp + fp)), (float(tp) / (tp + fn))
    return precision, recall


def _calculate_pr_curve(dict_log, dict_gt):
    '''
    calculate list of precision and recall values, for one given class
    '''
    lst_precision = []
    lst_recall = []
    lst_f1 = []
    lst_threshold = []
    for i in xrange(1, 100):
        tp = 0
        fp = 0
        fn = 0
        threshold = float(i) / 100    # not 0.01*i
        lst_threshold.append(threshold)
        for image in dict_log.keys():
            if image not in dict_gt:    # image check
                # print 'error: '+image
                continue
            elif _is_positive(dict_log[image], threshold) and dict_gt[image] == POSITIVE:
                tp += 1
            elif _is_positive(dict_log[image], threshold) and dict_gt[image] != POSITIVE:
                fp += 1
            elif not _is_positive(dict_log[image], threshold) and dict_gt[image] == POSITIVE:
                fn += 1
        if (tp + fp) == 0 or (tp + fn) == 0:
            fp, fn = float(1e-8), float(1e-8)
        lst_precision.append(float(tp) / (tp + fp))
        lst_recall.append(float(tp) / (tp + fn))
        lst_f1.append(float(2 * tp) / (2 * tp + fp + fn))
    AP = _calculate_ap(lst_recall, lst_precision)
    _draw_2d_curve(lst_recall, lst_precision, save_path=os.path.join(
        (args['<out-path>']), str(POSITIVE), 'pr-{}.png'.format(POSITIVE)), xlabel='Recall', ylabel='Precision')
    _draw_2d_curve(lst_threshold, lst_f1, save_path=os.path.join(
        (args['<out-path>']), str(POSITIVE), 'f1-{}.png'.format(POSITIVE)), xlabel='Threshold', ylabel='F1score')
    return lst_precision, lst_recall, lst_f1, lst_threshold, AP


def _calculate_accuracy(dict_log, dict_gt, err_log=None):
    '''
    calculate top-1 error
    '''
    total, tptn, tp, fp, fn, miss = 0, 0, 0, 0, 0, 0
    err_dic = dict()
    for image in dict_log.keys():
        total += 1

        # key check
        if image not in dict_gt:
            # print 'image not found in groundtruth file'
            miss += 1
            total -= 1
            continue

        # get image inference label
        if type(dict_log[image]['Top-1 Index']) == list:
            image_label = dict_log[image]['Top-1 Index'][0]
        elif type(dict_log[image]['Top-1 Index']) == int:
            image_label = dict_log[image]['Top-1 Index']

        # calculation
        if image_label == dict_gt[image]:
            tptn += 1
            if image_label == POSITIVE:
                tp += 1
        elif image_label != dict_gt[image] and image_label == POSITIVE:
            fp += 1
            # record error images
            err_dic[image] = dict_log[image].copy()
            err_dic[image]['Ground-truth Label'] = dict_gt[image]
        elif image_label != dict_gt[image] and dict_gt[image] == POSITIVE:
            fn += 1
            # record error images
            err_dic[image] = dict_log[image].copy()
            err_dic[image]['Ground-truth Label'] = dict_gt[image]

    logger.info('files: ' + str(len(dict_log.keys())))
    top_1_error = 1 - float(tptn) / total
    precision = float(tp) / (tp + fp)
    recall = float(tp) / (tp + fn)
    logger.info('missing files: ' + str(miss))
    if err_log:
        with open(err_log,'w') as f:
            json.dump(err_dic,f,indent=4)
    return top_1_error, precision, recall


def _convert_service_log(dict_log):
    '''
    convert pulp service log
    set nrop_flag = True if using nrop service
    '''
    dict_log_rslt = {}
    for key in dict_log.keys():
        dict_log_rslt[key] = {}
        if args['--nrop']:
            dict_log_rslt[key]['Top-1 Index'] = dict_log[key]['fileList'][0]['label']
        else:
            dict_log_rslt[key]['Top-1 Index'] = dict_log[key]['pulp']['fileList'][0]['result']['label']
        dict_log_rslt[key]['File Name'] = key
        dict_log_rslt[key]['Top-1 Class'] = None
        dict_log_rslt[key]['Confidence'] = None
    return dict_log_rslt


def _generate_model_evaluation_result(file_result, lst_precision, lst_recall, lst_f1, lst_threshold, (top_1_error, precision, recall), AP):
    file_result.write('Positive label: {}\n'.format(POSITIVE))
    file_result.write('Top-1 Error: {:.6f}\n'.format(top_1_error))
    file_result.write('Precision: {:.6f}\n'.format(precision))
    file_result.write('Recall: {:.6f}\n'.format(recall))
    file_result.write('Positive AP: {:.6f}\n'.format(AP))
    file_result.write('Thre\tPre \tRec \tF1 - score\n')
    for i in xrange(len(lst_threshold)):
        file_result.write('{:.2f}\t{:.4f}\t{:.4f}\t{:.4f}\n'.format(
            lst_threshold[i], lst_precision[i], lst_recall[i], lst_f1[i]))


def _generate_service_evaluation_result(file_result, precision, recall, top_1_error):
    file_result.write('Positive label: {}\n'.format(POSITIVE))
    file_result.write('Top-1 Error: {}\n'.format(top_1_error))
    file_result.write('Precision: {}\n'.format(precision))
    file_result.write('Recall: {}\n'.format(recall))


@_time_it.time_it
def main():
    global POSITIVE
    dict_gt = _read_list(args['--gt'])      # read groundtruth
    file_log = open(args['<in-log>'], 'r')
    dict_log = json.load(file_log)
    err_log = os.path.join(args['<out-path>'], 'err_img.log') if args['--err-log'] else None
    if args['--pos']:
        file_result = open(os.path.join(args['<out-path>'], str(POSITIVE), RESULT_FILE), 'w')
        POSITIVE = int(args['--pos'])
    # if args['--service']:
    #     dict_log=_convert_service_log(
    #         dict_log)   # convert online service log
    #     precision, recall=_calculate_pr(dict_log, dict_gt)
    #     _generate_service_evaluation_result(
    # file_result, precision, recall, _calculate_accuracy(dict_log, dict_gt))
    elif args['--all-labels']:
        assert args['--label-range'], 'please input label range!'
        for POSITIVE in xrange(int(args['--label-range'])):
            logger.info('positive label: {}'.format(POSITIVE))
            _check_path(os.path.join(args['<out-path>'], str(POSITIVE)))
            file_result = open(os.path.join(args['<out-path>'], str(POSITIVE), RESULT_FILE), 'w')
            lst_precision, lst_recall, lst_f1, lst_threshold, AP = _calculate_pr_curve(dict_log, dict_gt)
            _generate_model_evaluation_result(file_result, lst_precision, lst_recall,
                                              lst_f1, lst_threshold, _calculate_accuracy(dict_log, dict_gt, err_log), AP)
            file_result.close()
    else:
        lst_precision, lst_recall, lst_f1, lst_threshold, AP = _calculate_pr_curve(dict_log, dict_gt)
        _generate_model_evaluation_result(file_result, lst_precision, lst_recall,
                                          lst_f1, lst_threshold, _calculate_accuracy(dict_log, dict_gt, err_log), AP)
        file_result.close()
    file_log.close()


def unit_test():
    dict_gt = _read_list(args['--gt'])      # read groundtruth
    logger.debug(dict_gt)
    file_log = open(args['<in-log>'], 'r')
    dict_log = json.load(file_log)
    logger.debug('log successfully loaded')
    _draw_confusion_matrix(dict_log, dict_gt, 0)


if __name__ == '__main__':
    version = re.compile('.*\d+/\d+\s+(v[\d.]+)').findall(_init_.__doc__)[0]
    args = docopt.docopt(
        _init_.__doc__, version='mxnet training script {}'.format(version))
    _init_()
    logger.info('Start evaluation job...')
    main()
    # unit_test()
    logger.info('...done')
