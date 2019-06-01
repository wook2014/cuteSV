#!/usr/bin/env python

''' 
 * All rights Reserved, Designed By HIT-Bioinformatics   
 * @Title:  extract.py
 * @Package: argparse, pysam, sys, Bio, os, logging
 * @Description: Parse the ME signals from alignments
 * @author: tjiang
 * @date: Apr 24 2018
 * @version V1.0.0   
'''

import pysam
import cigar
from cuteSV_Description import parseArgs
from multiprocessing import Pool
from CommandRunner import *
# from resolution_type import * 
from cuteSV_resolveINV import run_inv
from cuteSV_resolveTRA import run_tra
from cuteSV_resolveINDEL import run_ins, run_del
from cuteSV_resolveDUP import run_dup
from cuteSV_genotype import generate_output
import os
import argparse
import logging
import sys
import time
import gc

dic_starnd = {1:'+', 2: '-'}
signal = {1 << 2: 0, \
		1 >> 1: 1, \
		1 << 4: 2, \
		1 << 11: 3, \
		1 << 4 | 1 << 11: 4}
'''
	1 >> 1 means normal_foward read
	1 << 2 means unmapped read
	1 << 4 means reverse_complement read
	1 << 11 means supplementary alignment read
	1 << 4 | 1 << 11 means supplementary alignment with reverse_complement read
'''
def detect_flag(Flag):
	back_sig = signal[Flag] if Flag in signal else 0
	return back_sig

def analysis_split_read(split_read, SV_size, RLength, read_name, candidate):
	'''
	read_start	read_end	ref_start	ref_end	chr	strand
	#0			#1			#2			#3		#4	#5
	'''
	SP_list = sorted(split_read, key = lambda x:x[0])
	# print(read_name)
	# for i in SP_list:
	# 	print(i)

	# detect INS involoved in a translocation
	trigger_INS_TRA = 0	

	for a in range(len(SP_list[:-1])):
		ele_1 = SP_list[a]
		ele_2 = SP_list[a+1]
		if ele_1[4] == ele_2[4]:
			# INV
			if ele_1[5] != ele_2[5]:
				# exist a bug 
				if ele_2[3] - ele_1[3] >= SV_size:
					if ele_2[0] >= ele_1[1]:
						if ele_1[4] not in candidate["INV"]:
							candidate["INV"][ele_1[4]] = list()
						candidate["INV"][ele_1[4]].append([ele_1[3], ele_2[3], read_name])
						candidate["INV"][ele_1[4]].append([ele_1[2], ele_2[2], read_name])

				if ele_1[3] - ele_2[3] >= SV_size:
					if ele_2[0] >= ele_1[1]:
						if ele_1[4] not in candidate["INV"]:
							candidate["INV"][ele_1[4]] = list()
						candidate["INV"][ele_1[4]].append([ele_2[3], ele_1[3], read_name])
						candidate["INV"][ele_1[4]].append([ele_2[2], ele_1[2], read_name])

			else:
				# dup & ins & del 
				if ele_1[5] == '-':
					ele_1 = [RLength-SP_list[a+1][1], RLength-SP_list[a+1][0]]+SP_list[a+1][2:]
					ele_2 = [RLength-SP_list[a][1],RLength-SP_list[a][0]]+SP_list[a][2:]

				if ele_1[3] - ele_2[2] >= SV_size and ele_2[0] - ele_1[1] <= 100:
					if ele_2[4] not in candidate["DUP"]:
						candidate["DUP"][ele_2[4]] = list()
					candidate["DUP"][ele_2[4]].append([ele_2[2], ele_1[3], read_name])

				if ele_1[3] - ele_2[2] < SV_size:
					if ele_2[0] + ele_1[3] - ele_2[2] - ele_1[1] >= SV_size:
						if ele_2[4] not in candidate["INS"]:
							candidate["INS"][ele_2[4]] = list()

						if ele_2[2] - ele_1[3] <= 100 and ele_2[0]+ele_1[3]-ele_2[2]-ele_1[1] <= 100000:
							candidate["INS"][ele_2[4]].append([(ele_2[2]+ele_1[3])/2, ele_2[0]+ele_1[3]-ele_2[2]-ele_1[1], read_name])
					if ele_2[2] - ele_2[0] + ele_1[1] - ele_1[3] >= SV_size:
						if ele_2[4] not in candidate["DEL"]:
							candidate["DEL"][ele_2[4]] = list()

						if ele_2[0] - ele_1[1] <= 100 and ele_2[2]-ele_2[0]+ele_1[1]-ele_1[3] <= 100000:
							candidate["DEL"][ele_2[4]].append([ele_1[3], ele_2[2]-ele_2[0]+ele_1[1]-ele_1[3], read_name])
		else:
			trigger_INS_TRA = 1
			'''
			*********Description*********
			*	TYPE A:		N[chr:pos[	*
			*	TYPE B:		N]chr:pos]	*
			*	TYPE C:		[chr:pos[N	*
			*	TYPE D:		]chr:pos]N	*
			*****************************
			'''
			if ele_2[0] - ele_1[1] <= 100:
				if ele_1[5] == '+':
					if ele_2[5] == '+':
						# +&+
						if ele_1[4] < ele_2[4]:
							if ele_1[4] not in candidate["TRA"]:
								candidate["TRA"][ele_1[4]] = list()
							candidate["TRA"][ele_1[4]].append(['A', ele_1[3], ele_2[4], ele_2[2], read_name])
							# N[chr:pos[
						else:
							if ele_2[4] not in candidate["TRA"]:
								candidate["TRA"][ele_2[4]] = list()
							candidate["TRA"][ele_2[4]].append(['D', ele_2[2], ele_1[4], ele_1[3], read_name])
							# ]chr:pos]N
					else:
						# +&-
						if ele_1[4] < ele_2[4]:
							if ele_1[4] not in candidate["TRA"]:
								candidate["TRA"][ele_1[4]] = list()
							candidate["TRA"][ele_1[4]].append(['B', ele_1[3], ele_2[4], ele_2[3], read_name])
							# N]chr:pos]
						else:
							if ele_2[4] not in candidate["TRA"]:
								candidate["TRA"][ele_2[4]] = list()
							candidate["TRA"][ele_2[4]].append(['B', ele_2[3], ele_1[4], ele_1[3], read_name])
							# N]chr:pos]
				else:
					if ele_2[5] == '+':
						# -&+
						if ele_1[4] < ele_2[4]:
							if ele_1[4] not in candidate["TRA"]:
								candidate["TRA"][ele_1[4]] = list()
							candidate["TRA"][ele_1[4]].append(['C', ele_1[2], ele_2[4], ele_2[2], read_name])
							# [chr:pos[N
						else:
							if ele_2[4] not in candidate["TRA"]:
								candidate["TRA"][ele_2[4]] = list()
							candidate["TRA"][ele_2[4]].append(['C', ele_2[2], ele_1[4], ele_1[2], read_name])
							# [chr:pos[N
					else:
						# -&-
						if ele_1[4] < ele_2[4]:
							if ele_1[4] not in candidate["TRA"]:
								candidate["TRA"][ele_1[4]] = list()
							candidate["TRA"][ele_1[4]].append(['D', ele_1[2], ele_2[4], ele_2[3], read_name])
							# ]chr:pos]N
						else:
							if ele_2[4] not in candidate["TRA"]:
								candidate["TRA"][ele_2[4]] = list()
							candidate["TRA"][ele_2[4]].append(['A', ele_2[3], ele_1[4], ele_1[2], read_name])
							# N[chr:pos[



	if len(SP_list) >= 3 and trigger_INS_TRA == 1:
		if SP_list[0][4] == SP_list[-1][4]:
			# print(SP_list[0])
			# print(SP_list[-1])
			if SP_list[0][5] != SP_list[-1][5]:
				pass
			else:
				if SP_list[0][5] == '+':
					ele_1 = SP_list[0]
					ele_2 = SP_list[-1]
				else:
					ele_1 = [RLength-SP_list[-1][1], RLength-SP_list[-1][0]]+SP_list[-1][2:]
					ele_2 = [RLength-SP_list[0][1],RLength-SP_list[0][0]]+SP_list[0][2:]
				# print(ele_1)
				# print(ele_2)
				dis_ref = ele_2[2] - ele_1[3]
				dis_read = ele_2[0] - ele_1[1]
				if dis_ref < 100 and dis_read - dis_ref >= SV_size and dis_read - dis_ref <= 100000:
					# print(min(ele_2[2], ele_1[3]), dis_read - dis_ref, read_name)
					if ele_1[4] not in candidate['INS']:
						candidate['INS'][ele_1[4]] = list()
					candidate["INS"][ele_2[4]].append([min(ele_2[2], ele_1[3]), dis_read - dis_ref, read_name])

				if dis_ref <= -SV_size:
					if ele_2[4] not in candidate["DUP"]:
						candidate["DUP"][ele_2[4]] = list()
					candidate["DUP"][ele_2[4]].append([ele_2[2], ele_1[3], read_name])

def acquire_clip_pos(deal_cigar):
	seq = list(cigar.Cigar(deal_cigar).items())
	if seq[0][1] == 'S':
		first_pos = seq[0][0]
	else:
		first_pos = 0
	if seq[-1][1] == 'S':
		last_pos = seq[-1][0]
	else:
		last_pos = 0

	bias = 0
	for i in seq:
		if i[1] == 'M' or i[1] == 'D' or i[1] == '=' or i[1] == 'X':
			bias += i[0]
	return [first_pos, last_pos, bias]

def organize_split_signal(chr, primary_info, Supplementary_info, total_L, low_bandary, 
	min_mapq, max_split_parts, read_name, candidate):
	split_read = list()
	if len(primary_info) > 0:
		split_read.append(primary_info)
		min_mapq = 0
	for i in Supplementary_info:
		seq = i.split(',')
		local_chr = seq[0]
		local_start = int(seq[1])
		local_cigar = seq[3]
		local_strand = seq[2]
		local_mapq = int(seq[4])
		if local_mapq >= min_mapq:
		# if local_mapq >= 0:	
			local_set = acquire_clip_pos(local_cigar)
			if local_strand == '+':
			 	split_read.append([local_set[0], total_L-local_set[1], local_start, 
			 		local_start+local_set[2], local_chr, local_strand])
			else:
				try:
					split_read.append([local_set[1], total_L-local_set[0], local_start, 
						local_start+local_set[2], local_chr, local_strand])
				except:
					pass
	if len(split_read) <= max_split_parts:
		analysis_split_read(split_read, low_bandary, total_L, read_name, candidate)

def generate_combine_sigs(sigs, Chr_name, read_name, svtype, candidate, merge_dis):
	# for i in sigs:
	# 	print(svtype,i, len(sigs))
	if len(sigs) == 0:
		pass
	elif len(sigs) == 1:
		if Chr_name not in candidate[svtype]:
			candidate[svtype][Chr_name] = list()
		candidate[svtype][Chr_name].append([sigs[0][0], 
											sigs[0][1], 
											read_name])
	else:
		temp_sig = sigs[0]
		if svtype == "INS":
			temp_sig += [sigs[0][0]]
		else:
			temp_sig += [sum(sigs[0])]
		# merge_dis_bias = max([i[1]] for i in sigs)

		for i in sigs[1:]:
			# if i[0] - temp_sig[2] <= max(merge_dis, merge_dis_bias):
			if i[0] - temp_sig[2] <= merge_dis:
				# 1000 ????
				temp_sig[1] += i[1]
				if svtype == "INS":
					temp_sig[2] = i[0]
				else:
					temp_sig[2] = sum(i)
			else:
				if Chr_name not in candidate[svtype]:
					candidate[svtype][Chr_name] = list()
				candidate[svtype][Chr_name].append([temp_sig[0], 
													temp_sig[1], 
													read_name])
				temp_sig = i
				temp_sig.append(i[0])

		if Chr_name not in candidate[svtype]:
			candidate[svtype][Chr_name] = list()
		candidate[svtype][Chr_name].append([temp_sig[0], 
											temp_sig[1], 
											read_name])


def parse_read(read, Chr_name, low_bandary, min_mapq, max_split_parts, min_read_len, candidate):
	if read.query_length < min_read_len:
		return 0

	Combine_sig_in_same_read_ins = list()
	Combine_sig_in_same_read_del = list()

	process_signal = detect_flag(read.flag)
	if read.mapq >= min_mapq:
		pos_start = read.reference_start
		pos_end = read.reference_end
		shift_del = 0
		shift_ins = 0
		softclip_left = 0
		softclip_right = 0
		for element in read.cigar:
			if element[0] in [0, 7 ,8]:
				shift_del += element[1]
			if element[0] == 2 and element[1] < low_bandary:
				shift_del += element[1]
			if element[0] == 2 and element[1] >= low_bandary:

				# if Chr_name not in candidate["DEL"]:
				# 	candidate["DEL"][Chr_name] = list()
				# candidate["DEL"][Chr_name].append([pos_start+shift_del, element[1], read.query_name])
				# print(Chr_name, pos_start+shift_del, element[1], read.query_name)
				Combine_sig_in_same_read_del.append([pos_start+shift_del, element[1]])
				shift_del += element[1]

			if element[0] in [0, 2, 7, 8]:
				shift_ins += element[1]
			if element[0] == 1 and element[1] >= low_bandary:
				shift_ins += 1
				# if Chr_name not in candidate["INS"]:
				# 	candidate["INS"][Chr_name] = list()
				# candidate["INS"][Chr_name].append([pos_start+shift_ins, element[1], read.query_name])
				# print(Chr_name, pos_start+shift_ins, element[1], read.query_name)
				Combine_sig_in_same_read_ins.append([pos_start+shift_ins, element[1]])

		if read.cigar[0][0] == 4:
			softclip_left = read.cigar[0][1]
		if read.cigar[-1][0] == 4:
			softclip_right = read.cigar[-1][1]

	# ************Combine signals in same read********************
	generate_combine_sigs(Combine_sig_in_same_read_ins, Chr_name, read.query_name, "INS", candidate, 500)
	generate_combine_sigs(Combine_sig_in_same_read_del, Chr_name, read.query_name, "DEL", candidate, 500)

	if process_signal == 1 or process_signal == 2:
		Tags = read.get_tags()
		if read.mapq >= min_mapq:
			if process_signal == 1:
				primary_info = [softclip_left, read.query_length-softclip_right, pos_start, 
				pos_end, Chr_name, dic_starnd[process_signal]]
			else:
				primary_info = [softclip_right, read.query_length-softclip_left, pos_start, 
				pos_end, Chr_name, dic_starnd[process_signal]]
		else:
			primary_info = []

		for i in Tags:
			if i[0] == 'SA':
				Supplementary_info = i[1].split(';')[:-1]
				organize_split_signal(Chr_name, primary_info, Supplementary_info, read.query_length, 
					low_bandary, min_mapq, max_split_parts, read.query_name, candidate)

def single_pipe(sam_path, min_length, min_mapq, max_split_parts, min_read_len, temp_dir, task):
	# args.input, args.min_length, args.min_mapq, args.max_split_parts, args.min_read_len, temporary_dir, i
	candidate = dict()
	candidate["DEL"] = dict()
	candidate["INS"] = dict()
	candidate["INV"] = dict()
	candidate["DUP"] = dict()
	candidate["TRA"] = dict()
	Chr_name = task[0]
	samfile = pysam.AlignmentFile(sam_path)
	Chr_length = samfile.get_reference_length(Chr_name)

	for read in samfile.fetch(Chr_name, task[1], task[2]):
		parse_read(read, Chr_name, min_length, min_mapq, max_split_parts, min_read_len, candidate)

	logging.info("Finished %s:%d-%d."%(Chr_name, task[1], task[2]))
	samfile.close()

	# os.mkdir("%ssignatures"%temp_dir)
	output = "%ssignatures/_%s_%d_%d.bed"%(temp_dir, Chr_name, task[1], task[2])
	file = open(output, 'w')
	for sv_type in ["DEL", "INS", "INV", "DUP", 'TRA']:
		try:
			for chr in candidate[sv_type]:
				# print candidate[sv_type][chr]
				for ele in candidate[sv_type][chr]:
					if len(ele) == 3:
						file.write("%s\t%s\t%d\t%d\t%s\n"%(sv_type, chr, ele[0], ele[1], ele[2]))
					elif len(ele) == 5:
						file.write("%s\t%s\t%s\t%d\t%s\t%d\t%s\n"%(sv_type, chr, ele[0], 
							ele[1], ele[2], ele[3], ele[4]))
		except:
			pass
	file.close()	


def multi_run_wrapper(args):
	return single_pipe(*args)

def main_ctrl(args):
	samfile = pysam.AlignmentFile(args.input)
	contig_num = len(samfile.get_index_statistics())
	logging.info("The total number of chromsomes: %d"%(contig_num))

	Task_list = list()
	chr_name_list = list()
	contigINFO = list()
	if args.temp_dir[-1] == '/':
		temporary_dir = args.temp_dir
	else:
		temporary_dir = args.temp_dir+'/'

	ref_ = samfile.get_index_statistics()
	for i in ref_:
		chr_name_list.append(i[0])
		local_ref_len = samfile.get_reference_length(i[0])
		contigINFO.append([i[0], local_ref_len])
		if local_ref_len < args.batches:
			Task_list.append([i[0], 0, local_ref_len])
		else:
			pos = 0
			task_round = int(local_ref_len/args.batches)
			for j in range(task_round):
				Task_list.append([i[0], pos, pos+args.batches])
				pos += args.batches
			if pos < local_ref_len:
				Task_list.append([i[0], pos, local_ref_len])

	# '''
	analysis_pools = Pool(processes=int(args.threads))
	os.mkdir("%ssignatures"%temporary_dir)
	for i in Task_list:
		para = [(args.input, args.min_length, args.min_mapq, args.max_split_parts, args.min_read_len, temporary_dir, i)]
		analysis_pools.map_async(multi_run_wrapper, para)
	analysis_pools.close()
	analysis_pools.join()
	# '''
	# '''
	logging.info("Rebuilding signatures of structural variants.")
	analysis_pools = Pool(processes=int(args.threads))
	cmd_del = ("cat %ssignatures/*.bed | grep DEL | sort -u | sort -k 2,2 -k 3,3n > %sDEL.sigs"%(temporary_dir, temporary_dir))
	cmd_ins = ("cat %ssignatures/*.bed | grep INS | sort -u | sort -k 2,2 -k 3,3n > %sINS.sigs"%(temporary_dir, temporary_dir))
	cmd_inv = ("cat %ssignatures/*.bed | grep INV | sort -u | sort -k 2,2 -k 3,3n > %sINV.sigs"%(temporary_dir, temporary_dir))
	cmd_tra = ("cat %ssignatures/*.bed | grep TRA | sort -u | sort -k 2,2 -k 5,5 -k 3,3 -k 4,4n > %sTRA.sigs"%(temporary_dir, temporary_dir))
	cmd_dup = ("cat %ssignatures/*.bed | grep DUP | sort -u | sort -k 1,1r -k 2,2 -k 3,4n > %sDUP.sigs"%(temporary_dir, temporary_dir))
	for i in [cmd_ins, cmd_del, cmd_dup, cmd_tra, cmd_inv]:
		analysis_pools.map_async(exe, (i,))
	analysis_pools.close()
	analysis_pools.join()
	# '''

	chr_name_list.sort()
	process_tra = list()
	for i in range(len(chr_name_list)-1):
		for j in chr_name_list[i+1:]:
			process_tra.append([chr_name_list[i], j])

	logging.info("Clustering structural variants.")
	analysis_pools = Pool(processes=int(args.threads))
	result = list()
	for chr in chr_name_list:
		for svtype in ["DEL", "INS", "INV"]:
			if svtype == "INV":
				para = [("%s%s.sigs"%(temporary_dir, svtype), chr, svtype, args.min_support, 
					args.max_cluster_bias_INV, args.min_length)]
				result.append(analysis_pools.map_async(run_inv, para))
				# pass
			if svtype == 'DEL':
				para = [("%s%s.sigs"%(temporary_dir, svtype), chr, svtype, args.min_support, 
					args.diff_ratio_merging_DEL, args.max_cluster_bias_DEL, args.diff_ratio_filtering_DEL, 
					min(args.min_support, 5))]
				result.append(analysis_pools.map_async(run_del, para))
			if svtype == 'INS':
				para = [("%s%s.sigs"%(temporary_dir, svtype), chr, svtype, args.min_support, 
					args.diff_ratio_merging_INS, args.max_cluster_bias_INS, args.diff_ratio_filtering_INS, 
					min(args.min_support, 5))]
				result.append(analysis_pools.map_async(run_ins, para))
		# DUP
		para = [("%s%s.sigs"%(temporary_dir, "DUP"), chr, args.min_support, args.max_cluster_bias_DUP, args.min_length)]
		result.append(analysis_pools.map_async(run_dup, para))

	for i in process_tra:
		# TRA
		para = [("%s%s.sigs"%(temporary_dir, "TRA"), i[0], i[1], args.min_support, 
			args.diff_ratio_filtering_TRA, args.max_cluster_bias_TRA)]
		result.append(analysis_pools.map_async(run_tra, para))

	analysis_pools.close()
	analysis_pools.join()

	semi_result = list()
	for res in result:
		try:
			semi_result += res.get()[0]
		except:
			pass

	logging.info("Writing into disk.")

	# sort SVs by [chr] and [pos]
	semi_result = sorted(semi_result, key = lambda x:(x[0], int(x[2])))
	generate_output(args, semi_result, contigINFO)	

	# logging.info("Cleaning temporary files.")
	# cmd_remove_tempfile = ("rm -r %ssignatures %s*.sigs"%(temporary_dir, temporary_dir))
	# exe(cmd_remove_tempfile)
	
	samfile.close()

def setupLogging(debug=False):
	logLevel = logging.DEBUG if debug else logging.INFO
	logFormat = "%(asctime)s [%(levelname)s] %(message)s"
	logging.basicConfig( stream=sys.stderr, level=logLevel, format=logFormat )
	logging.info("Running %s" % " ".join(sys.argv))


def run(argv):
	args = parseArgs(argv)
	setupLogging(False)
	starttime = time.time()
	main_ctrl(args)
	logging.info("Finished in %0.2f seconds."%(time.time() - starttime))

if __name__ == '__main__':
	run(sys.argv[1:])
